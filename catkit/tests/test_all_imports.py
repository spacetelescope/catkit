import glob
import importlib
import os
import platform

import pytest

import catkit

# Find package root dir path.
package_path = os.path.dirname(catkit.__file__)
# Find all .py files in package root path.
search_pattern = os.path.join(package_path, "**", "*.py")
all_files = glob.glob(search_pattern, recursive=True)
# Keep only those files that are actual files (not dirs) and are not __init__.py files.
all_files = [f for f in all_files if os.path.isfile(f) and os.path.basename(f) != "__init__.py"]
# Remove the package root path from all of the file paths.
all_files = [os.path.relpath(f, start=os.path.join(package_path, "..")) for f in all_files]
all_imports = []
for item in all_files:
    # Convert file system paths to python imports.
    replace = "\\" if platform.system() == "Windows" else "/"
    all_imports.append(os.path.normpath(os.path.splitext(item)[0]).replace(replace, "."))

# Ignore known ImportErrors due to missing 3rd party drivers.
exclude_exceptions_containing = ["zwoas",
                                 "bmc",
                                 "TSP01",
                                 "libftd2xx"]


@pytest.mark.parametrize("to_import", all_imports)
def test_imports(to_import):
    if any(exclusion in str(to_import) for exclusion in exclude_exceptions_containing):
        return

    try:
        importlib.__import__(to_import)
    except ImportError as error:
        if not any(exclusion in str(error) for exclusion in exclude_exceptions_containing):
            raise


