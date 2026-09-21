from src.s3_backup import backup_state


def test_compute_dir_size_bytes_sums_files(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"x" * 100)
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_bytes(b"y" * 50)

    assert backup_state.compute_dir_size_bytes(str(tmp_path)) == 150


def test_compute_dir_size_bytes_ignores_state_file(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"x" * 100)
    backup_state.write_state(str(tmp_path), 100)

    assert backup_state.compute_dir_size_bytes(str(tmp_path)) == 100


def test_read_previous_total_bytes_none_when_missing(tmp_path):
    assert backup_state.read_previous_total_bytes(str(tmp_path)) is None


def test_write_then_read_state_roundtrip(tmp_path):
    backup_state.write_state(str(tmp_path), 12345)

    assert backup_state.read_previous_total_bytes(str(tmp_path)) == 12345


def test_dir_has_entries_false_on_empty_dir(tmp_path):
    assert backup_state.dir_has_entries(str(tmp_path)) is False


def test_dir_has_entries_false_when_only_state_file_present(tmp_path):
    backup_state.write_state(str(tmp_path), 100)

    assert backup_state.dir_has_entries(str(tmp_path)) is False


def test_dir_has_entries_true_with_a_real_file(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"x")

    assert backup_state.dir_has_entries(str(tmp_path)) is True


def test_dir_has_entries_true_with_only_a_subdirectory(tmp_path):
    (tmp_path / "sub").mkdir()

    assert backup_state.dir_has_entries(str(tmp_path)) is True


def test_dir_has_entries_false_for_nonexistent_path(tmp_path):
    assert backup_state.dir_has_entries(str(tmp_path / "does-not-exist")) is False


def test_dir_has_entries_stops_at_first_match(tmp_path, monkeypatch):
    """Must not need to enumerate every entry — one hit is enough to return."""
    (tmp_path / "a.txt").write_bytes(b"x")
    (tmp_path / "b.txt").write_bytes(b"y")

    real_scandir = backup_state.os.scandir
    calls = []

    def counting_scandir(path):
        calls.append(path)
        return real_scandir(path)

    monkeypatch.setattr(backup_state.os, "scandir", counting_scandir)

    assert backup_state.dir_has_entries(str(tmp_path)) is True
    assert len(calls) == 1
