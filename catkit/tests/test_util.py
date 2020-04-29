import glob
import os

import numpy as np
import pytest
from astropy.io import fits

import catkit.util

class TestSaveImages:

    def test_empty_image_list(self, tmpdir):
        # Check that for NULL return.
        assert(catkit.util.save_images([], None, tmpdir, "dummy.fits") is None)
        # Check that no files were written.
        assert(not os.path.exists(os.path.join(tmpdir, "dummy.fits")))
        assert(not glob.glob(os.path.join(tmpdir, "*.fits")))

    @pytest.mark.parametrize("base_filename", ("dummy", "dummy.fits"))
    def test_auto_ext(self, base_filename, tmpdir):
        catkit.util.save_images([np.zeros((5, 5))], None, tmpdir, base_filename)
        assert(os.path.isfile(os.path.join(tmpdir, f"{os.path.splitext(base_filename)[0]}.fits")))

    @pytest.mark.parametrize("num_images", (1, 2, 5))
    def test_file_numbering(self, num_images, tmpdir):
        image = np.zeros((5, 5))
        image_list = []
        for i in range(num_images):
            image_list.append(image)
        catkit.util.save_images(image_list, None, tmpdir, "dummy.fits")
        for i in range(num_images):
            frame = f"_frame{i + 1}" if num_images > 1 else ''
            assert(os.path.isfile(os.path.join(tmpdir, f"dummy{frame}.fits")))

        # Check that the above are the only files.
        assert(len(glob.glob(os.path.join(tmpdir, "*.fits"))) == num_images)

    @pytest.mark.parametrize("raw_skip", (0, 1, 2, 3, 4, 5))
    def test_raw_skip(self, raw_skip, tmpdir):
        image = np.zeros((5, 5))
        image_list = []
        for i in range(2 + raw_skip * 10):
            image_list.append(image)

        catkit.util.save_images(image_list, None, tmpdir, "dummy.fits", raw_skip=raw_skip)

        # raw_skip works in that a raw_skip number of files are not written for everyone that is.
        # Every 1 + i + i*raw_skip file is written.
        # E.g.,
        # raw_skip = 0: (write all, skip none)
        # raw_skip = 1: write, skip, write, skip, write, ...
        # raw_skip = 2: write, skip, skip, write, skip, skip, write, ...
        # raw_skip > num_images: (write 1st, skip rest). See self.test_skip_all_but_one()
        # One way to look at this is that at least 1 files is always written so min(expected_file_count) >= 1.
        # Then the sequence length is actually raw_skip + 1 as you include the file written.
        # The skip sequence doesn't start until the 1st file is written so there are only len(image_list)-1 remaining
        # files to apply the sequence to.
        expected_file_count = 1 + (len(image_list)-1) // (raw_skip + 1)

        for i in range(expected_file_count):
            frame = f"_frame{1 + i + i*raw_skip}" if expected_file_count > 1 else ''
            print(frame)
            assert (os.path.isfile(os.path.join(tmpdir, f"dummy{frame}.fits")))

        # Check that the above are the only files.
        assert(len(glob.glob(os.path.join(tmpdir, "*.fits"))) == expected_file_count)

    def test_skip_all_but_one(self, tmpdir):
        image = np.zeros((5, 5))
        image_list = []
        for i in range(10):
            image_list.append(image)

        catkit.util.save_images(image_list, None, tmpdir, "dummy.fits", raw_skip=len(image_list)+1)
        assert(len(glob.glob(os.path.join(tmpdir, "*.fits"))) == 1)

    def test_header_path_keyword(self, tmpdir):
        catkit.util.save_images([np.zeros((5, 5))], None, tmpdir, "dummy.fits")
        header = fits.getheader(os.path.join(tmpdir, "dummy.fits"))
        assert(header.get("PATH"))
        assert(os.path.isfile(header["PATH"]))

    def test_meta_path_keyword(self, tmpdir):
        meta_data = []
        catkit.util.save_images([np.zeros((5, 5))], meta_data, tmpdir, "dummy.fits")
        assert(meta_data)
        assert(meta_data[0].name == "PATH")
        assert(os.path.isfile(meta_data[0].value))
