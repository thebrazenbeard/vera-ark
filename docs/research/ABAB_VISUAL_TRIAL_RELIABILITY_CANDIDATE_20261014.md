# ARK ABAB visual-trial reliability candidate

Status: offline research only. No live controller output, gameplay claim, or runtime activation.

An IDLE/ACTION/IDLE/ACTION evidence packet can be evaluated in two separate tiers: receipt-only structural checks, and frame-bound checks against eight normalized PNG byte streams. Receipt-only evidence never yields a frame-bound candidate. Frame binding checks SHA-256 identity, PNG CRC/order, decompression and dimensions; it does not authenticate capture origin or recompute optical flow.

The candidate implementation and synthetic tests are staged as an external reviewed artifact pending safe source-file upload. Do not run untrusted workspace folder-open tasks.

Hostile review: fabricated PNG frames and self-reported median optical flow can still pass. No independent reviewer, real-system capture, verified yaw, or authority to execute was established.