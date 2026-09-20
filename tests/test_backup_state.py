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


def test_looks_suspiciously_smaller_true_on_big_drop():
    assert backup_state.looks_suspiciously_smaller(100, 1000, ratio=0.5) is True


def test_looks_suspiciously_smaller_false_on_small_drop():
    assert backup_state.looks_suspiciously_smaller(900, 1000, ratio=0.5) is False


def test_looks_suspiciously_smaller_false_when_growing():
    assert backup_state.looks_suspiciously_smaller(2000, 1000, ratio=0.5) is False


def test_looks_suspiciously_smaller_false_when_no_previous_history():
    assert backup_state.looks_suspiciously_smaller(0, 0, ratio=0.5) is False
