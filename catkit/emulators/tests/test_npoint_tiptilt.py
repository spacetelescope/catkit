import os

from catkit.emulators.npoint_tiptilt import SimnPointTipTiltController

vendor_id = 1027
product_id = 24596


def test_init():
    SimnPointTipTiltController(config_id="npoint_tiptilt_lc_400",
                               vendor_id=vendor_id,
                               product_id=product_id,
                               library_path=os.path.abspath(__file__))
