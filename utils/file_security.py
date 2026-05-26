import os


def build_safe_file_path(base_dir, filename, suffix=".json"):
    if not filename or filename != os.path.basename(filename):
        raise ValueError("invalid filename")
    if ".." in filename or filename.startswith("/") or filename.startswith("\\"):
        raise ValueError("invalid filename")
    if suffix and not filename.endswith(suffix):
        raise ValueError(f"only {suffix} is allowed")

    base_root = os.path.abspath(base_dir)
    file_path = os.path.abspath(os.path.join(base_dir, filename))
    if os.path.commonpath([base_root, file_path]) != base_root:
        raise ValueError("invalid file path")
    return file_path
