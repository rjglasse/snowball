"""Tests for JSON storage functionality."""

import json

from snowball.storage.json_storage import JSONStorage
from snowball.models import PaperStatus


class TestJSONStorage:
    """Tests for JSONStorage class."""

    def test_init_creates_directories(self, temp_project_dir):
        """Test that init creates necessary directories."""
        storage = JSONStorage(temp_project_dir)
        assert storage.project_dir.exists()
        assert storage.papers_dir.exists()

    def test_init_with_nonexistent_dir(self, temp_project_dir):
        """Test that init creates parent directories if needed."""
        new_dir = temp_project_dir / "nested" / "path"
        storage = JSONStorage(new_dir)
        assert storage.project_dir.exists()

    def test_generate_id(self):
        """Test that generate_id creates unique UUIDs."""
        id1 = JSONStorage.generate_id()
        id2 = JSONStorage.generate_id()
        assert id1 != id2
        assert len(id1) == 36  # UUID format

    def test_save_and_load_project(self, storage, sample_project):
        """Test saving and loading a project."""
        storage.save_project(sample_project)
        loaded = storage.load_project()
        
        assert loaded is not None
        assert loaded.name == sample_project.name
        assert loaded.description == sample_project.description
        assert loaded.max_iterations == sample_project.max_iterations

    def test_load_project_not_found(self, storage):
        """Test loading project when none exists."""
        loaded = storage.load_project()
        assert loaded is None

    def test_save_project_updates_timestamp(self, storage, sample_project):
        """Test that saving project updates the updated_at timestamp."""
        storage.save_project(sample_project)
        loaded = storage.load_project()
        # The updated_at should be set during save
        assert loaded.updated_at is not None

    def test_save_and_load_paper(self, storage, sample_paper):
        """Test saving and loading a single paper."""
        storage.save_paper(sample_paper)
        loaded = storage.load_paper(sample_paper.id)
        
        assert loaded is not None
        assert loaded.id == sample_paper.id
        assert loaded.title == sample_paper.title
        assert loaded.doi == sample_paper.doi

    def test_load_paper_not_found(self, storage):
        """Test loading paper that doesn't exist."""
        loaded = storage.load_paper("nonexistent-id")
        assert loaded is None

    def test_save_papers_bulk(self, storage, sample_papers):
        """Test saving multiple papers at once."""
        storage.save_papers(sample_papers)
        
        for paper in sample_papers:
            loaded = storage.load_paper(paper.id)
            assert loaded is not None
            assert loaded.id == paper.id

    def test_load_all_papers(self, storage_with_papers, sample_papers):
        """Test loading all papers."""
        loaded = storage_with_papers.load_all_papers()
        assert len(loaded) == len(sample_papers)
        
        loaded_ids = {p.id for p in loaded}
        expected_ids = {p.id for p in sample_papers}
        assert loaded_ids == expected_ids

    def test_load_all_papers_empty(self, storage):
        """Test loading all papers when none exist."""
        loaded = storage.load_all_papers()
        assert loaded == []

    def test_get_papers_by_status(self, storage_with_papers):
        """Test filtering papers by status."""
        included = storage_with_papers.get_papers_by_status(PaperStatus.INCLUDED)
        assert len(included) == 1
        assert all(p.status == PaperStatus.INCLUDED for p in included)

        pending = storage_with_papers.get_papers_by_status(PaperStatus.PENDING)
        assert len(pending) == 1

    def test_get_papers_by_iteration(self, storage_with_papers):
        """Test filtering papers by iteration."""
        iteration_0 = storage_with_papers.get_papers_by_iteration(0)
        assert len(iteration_0) == 1
        
        iteration_1 = storage_with_papers.get_papers_by_iteration(1)
        assert len(iteration_1) == 2

    def test_update_paper_status(self, storage, sample_paper):
        """Test updating a paper's status."""
        storage.save_paper(sample_paper)
        storage.update_paper_status(sample_paper.id, PaperStatus.INCLUDED, "Good paper")
        
        loaded = storage.load_paper(sample_paper.id)
        assert loaded.status == PaperStatus.INCLUDED
        assert loaded.notes == "Good paper"
        assert loaded.review_date is not None

    def test_update_paper_status_nonexistent(self, storage):
        """Test updating status of nonexistent paper does nothing."""
        # This should not raise an error
        storage.update_paper_status("nonexistent", PaperStatus.INCLUDED)

    def test_get_statistics(self, storage_with_papers, sample_papers):
        """Test getting statistics about papers."""
        stats = storage_with_papers.get_statistics()
        
        assert stats["total"] == len(sample_papers)
        assert "by_status" in stats
        assert "by_iteration" in stats
        assert "by_source" in stats

    def test_get_statistics_by_status(self, storage_with_papers):
        """Test statistics by status breakdown."""
        stats = storage_with_papers.get_statistics()
        by_status = stats["by_status"]
        
        assert by_status.get("included", 0) == 1
        assert by_status.get("pending", 0) == 1
        assert by_status.get("excluded", 0) == 1
        assert by_status.get("maybe", 0) == 1

    def test_get_statistics_empty(self, storage):
        """Test statistics when no papers exist."""
        stats = storage.get_statistics()
        assert stats["total"] == 0
        assert stats["by_status"] == {}

    def test_find_paper_by_doi(self, storage_with_papers):
        """Test finding a paper by DOI."""
        found = storage_with_papers.find_paper_by_doi("10.1234/paper1")
        assert found is not None
        assert found.title == "Machine Learning in Healthcare"

    def test_find_paper_by_doi_case_insensitive(self, storage_with_papers):
        """Test that DOI search is case-insensitive."""
        found = storage_with_papers.find_paper_by_doi("10.1234/PAPER1")
        assert found is not None

    def test_find_paper_by_doi_not_found(self, storage_with_papers):
        """Test finding paper by nonexistent DOI."""
        found = storage_with_papers.find_paper_by_doi("10.9999/nonexistent")
        assert found is None

    def test_find_paper_by_title(self, storage_with_papers):
        """Test finding a paper by title."""
        found = storage_with_papers.find_paper_by_title("Machine Learning in Healthcare")
        assert found is not None
        assert found.doi == "10.1234/paper1"

    def test_find_paper_by_title_case_insensitive(self, storage_with_papers):
        """Test that title search is case-insensitive."""
        found = storage_with_papers.find_paper_by_title("machine learning in healthcare")
        assert found is not None

    def test_find_paper_by_title_not_found(self, storage_with_papers):
        """Test finding paper by nonexistent title."""
        found = storage_with_papers.find_paper_by_title("Nonexistent Paper Title")
        assert found is None

    def test_paper_file_location(self, storage, sample_paper):
        """Test that papers are saved to correct file location."""
        storage.save_paper(sample_paper)
        paper_file = storage.papers_dir / f"{sample_paper.id}.json"
        assert paper_file.exists()

    def test_paper_file_is_valid_json(self, storage, sample_paper):
        """Test that saved paper file contains valid JSON."""
        storage.save_paper(sample_paper)
        paper_file = storage.papers_dir / f"{sample_paper.id}.json"
        
        with open(paper_file, 'r') as f:
            data = json.load(f)
        
        assert data["id"] == sample_paper.id
        assert data["title"] == sample_paper.title

    def test_project_file_location(self, storage, sample_project):
        """Test that project is saved to correct file location."""
        storage.save_project(sample_project)
        assert storage.project_file.exists()

    def test_papers_index_created(self, storage, sample_papers):
        """Test that papers index file is created."""
        storage.save_papers(sample_papers)
        assert storage.papers_file.exists()

    def test_papers_index_contains_metadata(self, storage, sample_papers):
        """Test that papers index contains key metadata."""
        storage.save_papers(sample_papers)
        
        with open(storage.papers_file, 'r') as f:
            index = json.load(f)
        
        assert len(index) == len(sample_papers)
        for paper in sample_papers:
            assert paper.id in index
            assert "title" in index[paper.id]
            assert "status" in index[paper.id]
