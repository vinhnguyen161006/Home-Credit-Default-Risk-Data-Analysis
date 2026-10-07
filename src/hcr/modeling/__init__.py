"""Step 7: baselines, cross-validated training, calibration and thresholding.

Every data-dependent transform lives inside a scikit-learn Pipeline so it fits
within the fold. The constant-rate and EXT_SOURCE-only baselines are mandatory:
without them the final number has no frame of reference.
"""
