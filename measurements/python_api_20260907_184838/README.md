# OWON VDS1022I Python API verification — 2026-09-07

CH1 was connected to the oscilloscope's nominal 1 kHz / 5 V probe-check output, with the physical probe at x1. The OWON Java application was closed through its SCPI shutdown command before direct USB access. No fan actuation or firmware update was performed in this test.

Device: VDS1022I23440320; reported hardware version V5.0.1; Python USB backend libusb0. The vendored florentbr/OWON-VDS1022 API was used.

Settings: CH1 DC, probe=1, 10 V full range, offset=0.25, rising-edge trigger at 2 V, AUTO. Tested 250 kS/s and 1.25 MS/s, three retained acquisitions of 5,000 samples at each rate. The first acquisition after each configuration change was discarded, followed by 0.3 s settling time.

All six retained acquisitions showed a stable square wave:

- Sample-derived frequency: 1,000 Hz at both sample rates.
- Device frequency counter: approximately 999.99994–1,000.00006 Hz.
- Low plateau (10th percentile): −0.02 V.
- High plateau (90th percentile): 4.86 V.
- High duty: 49.84–50.00%.
- No ADC saturation.

This verifies acquisition functionality with the internal reference. It is not an independent calibration of absolute voltage or timebase accuracy. Previous SCPI estimates around 4 V and the inferred four-record payload structure were not sufficiently verified and must not be treated as reference measurements. The cause of the earlier Tach acquisition failure remains unresolved until the Tach node is tested again.

The test script constructs sample times as arange(N)/sampling_rate. Upstream Frame.x() uses inclusive linspace endpoints, introducing about 0.02% time-axis scaling error for 5,000 samples. The vendored library itself was not changed.

Files: summary.json contains numerical results; each CSV contains time, voltage, and raw ADC values; PNG files show the third retained acquisition at each sample rate. Reproduction script: ../../hardware/verify_vds_python_api.py. USB resources were released at completion. The OWON GUI remains closed for subsequent Python acquisition.
