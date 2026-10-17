# ARK order-cell replication and leave-one-pair-out sensitivity — T33

**Subject:** isolated, offline-only diagnostic; `src/vera_ark/offline_order_sensitivity.py`.

The previous T32 order-standardized score can be numerically defined with only one declared pair per first-arm cell. Removing that pair makes the cell unobservable. This diagnostic reports the minimum cell size, number of cells below two, and a leave-one-pair-out range **only when every group has at least two pairs for each first-arm assignment**. All groups remain equally weighted after each deletion. A zero crossing marks a fragile directional claim.

Inputs are caller-supplied holdout paired deltas, not verified observations. The diagnostic intentionally does not accept development data, authenticate order chronology, validate upstream manifest/evidence, or certify preregistration. It is meant to consume *previously validated* holdout pairs, not replace T32's plan/evidence checks. Even a stable sign is not statistical significance, randomization, learning, or causal effect.

A synthetic two-group fixture has standardized delta +0.25 but single-pair deletion range [0, +0.5], so the directional sign is not robust. One-pair-per-order counterbalancing reports the adjusted score but no leave-one-out estimate; missing first-arm cells suppress adjusted scores entirely.

**Boundaries:** No live controller, Remote Play, game scene, installed runtime, credential, or protected effect. Internal model review only. Independent review required before broader interpretation.
