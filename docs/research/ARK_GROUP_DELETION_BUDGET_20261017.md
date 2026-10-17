# ARK T35: offline scene-group deletion-budget sensitivity

Research only. Tested local candidate, not installed or live. Source baseline vera-ark/main@7e4b8469; vera-mono/main@16a2828d. No overlap with open PRs #12-14, #21-22.

Five synthetic groups (+0.9,+0.9,-0.1,-0.1,-0.1) have macro +0.30; deleting one group leaves minimum +0.15, but deleting both positive groups gives -0.10. A one-group deletion diagnostic can miss this two-group reversal. The standalone evaluator requires both declared first-arm cells per group and computes exact min/max macro deltas for deletion of zero through k whole groups, retaining at least two groups.

Caller-supplied group IDs, order, rewards, and deletion budget are not authenticated. A posthoc budget can be cherry-picked. This is descriptive sensitivity, not statistical significance, actual gameplay, independent review, or causal learning. Source/tests remain local until published and independently reviewed.
