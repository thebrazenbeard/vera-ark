# T68 — caller-supplied capture byte binding

Independent, source-only offline verifier. Accepts the exact serialized T67-style observation envelope and capture bytes; checks strict JSON decoding, duplicate keys, declared experiment/trial identity, a separately expected SHA-256, and the digest of the supplied capture bytes. No controller, file, network, or image-decoder side effect. The verifier deliberately does not import T65–T67: its narrow check can be tested and reviewed independently while their publication remains incomplete.

**Claim ceiling:** self-consistency of caller-supplied capture bytes and digest declarations only. This function does not validate T67 metric semantics, T65/T66 witness signatures, trusted time, independent witness custody, image decoding, capture origin/currentness, controller causality, or gameplay learning. A fabricated capture and matching caller-issued digest passes by design. Compose only after separately verifying the other surfaces; no claim is elevated by composition.

Synthetic adversarial regressions cover byte substitution, changed declarations, wrong identity, duplicate JSON keys, invalid UTF-8, nonfinite constants, oversized/empty captures, and a positive fabricated-artifact counterexample. Tests are not gameplay evidence. No delegated PR subjects, runtime, main, driver, or protected effects touched.
