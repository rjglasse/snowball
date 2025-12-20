"""Graph visualization for the citation network."""

from datetime import datetime
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Paper

# Muted dark mode color palette for edges - stylish and distinguishable
EDGE_PALETTE = [
    "#7eb8da",  # soft sky blue
    "#a8d4a2",  # muted sage
    "#e6b89c",  # warm peach
    "#b8a9c9",  # dusty lavender
    "#8ecdc8",  # soft teal
    "#dba8a8",  # muted rose
    "#c9c9a1",  # soft olive
    "#a3c4bc",  # seafoam
    "#d4a8c4",  # dusty pink
    "#b8c9d4",  # pale steel
    "#c9b8a3",  # warm sand
    "#a8b8c9",  # cool grey-blue
    "#c4d4a8",  # soft lime
    "#d4b8c4",  # mauve
    "#a8c9b8",  # mint
    "#c9a8b8",  # dusty rose
]


def generate_citation_graph(
    papers: List["Paper"],
    output_dir: Path,
    title: str = "Citation Network",
    included_only: bool = True,
) -> Optional[Path]:
    """Generate a visualization of the citation network.

    Creates a left-to-right hierarchical graph where:
    - X position = iteration (seeds on left, later iterations to the right)
    - Only included papers are shown (by default)
    - Node size reflects citation count

    Args:
        papers: List of all papers in the project
        output_dir: Directory to save the visualization
        title: Title for the graph
        included_only: If True, only show included papers (default True)

    Returns:
        Path to the generated PNG file, or None if visualization libraries unavailable
    """
    try:
        import networkx as nx
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    # Filter to included papers only
    if included_only:
        papers = [p for p in papers if _get_status(p) == "included"]

    if not papers:
        return None

    # Build paper lookup for edge creation
    paper_lookup = {p.id: p for p in papers}
    paper_ids = set(paper_lookup.keys())

    # Create the graph
    G = nx.DiGraph()

    # Add nodes
    for paper in papers:
        citations = paper.citation_count or 0

        # Wrap title at ~30 chars per line
        paper_title = paper.title
        wrapped_title = _wrap_text(paper_title, width=30)

        G.add_node(
            paper.id,
            label=wrapped_title,
            full_title=paper_title,
            iteration=paper.snowball_iteration,
            citations=citations,
        )

    # Add edges (only between included papers)
    for paper in papers:
        for source_id in paper.source_paper_ids:
            if source_id in paper_ids:
                G.add_edge(source_id, paper.id)

    if len(G.nodes()) == 0:
        return None

    # Group nodes by iteration
    iterations = {}
    for node, data in G.nodes(data=True):
        iter_num = data.get("iteration", 0)
        if iter_num not in iterations:
            iterations[iter_num] = []
        iterations[iter_num].append(node)

    # Sort nodes within each iteration by citation count (highest at top)
    for iter_num in iterations:
        iterations[iter_num].sort(
            key=lambda n: G.nodes[n].get("citations", 0),
            reverse=True
        )

    # Calculate figure size based on content (keep reasonable for 600 DPI)
    max_per_column = max(len(nodes) for nodes in iterations.values()) if iterations else 1
    num_iterations = len(iterations)
    fig_width = min(24, max(16, num_iterations * 5))
    fig_height = min(18, max(10, max_per_column * 2))

    # Create figure
    fig, ax = plt.subplots(1, 1, figsize=(fig_width, fig_height), facecolor="#0d1117")
    ax.set_facecolor("#0d1117")

    # Calculate positions: left-to-right by iteration
    pos = {}
    x_spacing = 6  # Horizontal spacing between iterations
    y_spacing = 3  # Vertical spacing between nodes in same iteration

    for iter_num in sorted(iterations.keys()):
        nodes = iterations[iter_num]
        x = iter_num * x_spacing

        # Center nodes vertically
        total_height = (len(nodes) - 1) * y_spacing
        start_y = total_height / 2

        for i, node in enumerate(nodes):
            y = start_y - (i * y_spacing)
            pos[node] = (x, y)

    labels = {n: G.nodes[n]["label"] for n in G.nodes()}

    # Estimate text widths for edge positioning (approximate based on char count)
    text_half_widths = {}
    padding = 0.3  # Padding between text and edge connection point
    for node in G.nodes():
        label = labels[node]
        max_line_len = max(len(line) for line in label.split('\n'))
        text_half_widths[node] = max_line_len * 0.04 + padding

    # Assign colors to source papers (papers that have outgoing edges)
    source_nodes = sorted(set(source for source, _ in G.edges()))
    source_colors = {
        node: EDGE_PALETTE[i % len(EDGE_PALETTE)]
        for i, node in enumerate(source_nodes)
    }

    # Draw edges with elbow-style connectors (arrive horizontally)
    from matplotlib.path import Path as MplPath
    import matplotlib.patches as mpatches

    for source, target in G.edges():
        src_x, src_y = pos[source]
        tgt_x, tgt_y = pos[target]

        # Get color for this source paper
        edge_color = source_colors.get(source, EDGE_PALETTE[0])

        # Offset: start from right edge of source, end at left edge of target
        src_x_offset = src_x + text_half_widths[source]
        tgt_x_offset = tgt_x - text_half_widths[target]

        # Control point offset (determines curve tension)
        ctrl_offset = (tgt_x_offset - src_x_offset) * 0.4

        # Cubic Bézier: P0 -> P1 -> P2 -> P3
        # P1 is right of P0 (horizontal departure)
        # P2 is left of P3 (horizontal arrival)
        verts = [
            (src_x_offset, src_y),                    # P0: start
            (src_x_offset + ctrl_offset, src_y),      # P1: control (horizontal out)
            (tgt_x_offset - ctrl_offset, tgt_y),      # P2: control (horizontal in)
            (tgt_x_offset, tgt_y),                    # P3: end
        ]
        codes = [MplPath.MOVETO, MplPath.CURVE4, MplPath.CURVE4, MplPath.CURVE4]
        path = MplPath(verts, codes)

        # Draw the S-curve
        patch = mpatches.PathPatch(
            path,
            facecolor='none',
            edgecolor=edge_color,
            alpha=0.6,
            linewidth=1.5,
        )
        ax.add_patch(patch)

        # Add arrowhead at target (pointing right/horizontal)
        arrow_size = 0.15
        ax.annotate(
            '',
            xy=(tgt_x_offset, tgt_y),
            xytext=(tgt_x_offset - arrow_size, tgt_y),
            arrowprops=dict(
                arrowstyle='-|>',
                color=edge_color,
                alpha=0.6,
                lw=1.5,
                mutation_scale=10,
            ),
        )

    # Draw labels only (no nodes) - use text directly for better control
    for node, (x, y) in pos.items():
        ax.text(
            x, y,
            labels[node],
            fontsize=9,
            color="#c9d1d9",
            fontweight="bold",
            ha="center",
            va="center",
            multialignment="center",
        )

    # Set axis limits based on data
    all_x = [p[0] for p in pos.values()]
    all_y = [p[1] for p in pos.values()]
    margin = 1.5
    ax.set_xlim(min(all_x) - margin, max(all_x) + margin)
    ax.set_ylim(min(all_y) - margin, max(all_y) + margin)

    ax.axis("off")
    plt.tight_layout()

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"citation_graph_{timestamp}.png"

    # Save PNG at screen resolution
    plt.savefig(
        output_file,
        dpi=150,
        facecolor="#0d1117",
        edgecolor="none",
        bbox_inches="tight",
        pad_inches=0.5,
    )
    plt.close(fig)

    return output_file


def _get_status(paper) -> str:
    """Get status value as string."""
    status = paper.status
    return status.value if hasattr(status, "value") else status


def _wrap_text(text: str, width: int = 30) -> str:
    """Wrap text at word boundaries to fit within width.

    Args:
        text: Text to wrap
        width: Maximum characters per line

    Returns:
        Text with newlines inserted at word boundaries
    """
    words = text.split()
    lines = []
    current_line = []
    current_length = 0

    for word in words:
        if current_length + len(word) + (1 if current_line else 0) <= width:
            current_line.append(word)
            current_length += len(word) + (1 if len(current_line) > 1 else 0)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
            current_length = len(word)

    if current_line:
        lines.append(" ".join(current_line))

    return "\n".join(lines)
