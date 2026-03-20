"""Role assignment engine.

Decides which agents act as implementers vs. reviewers each round.
Supports static, round-robin, and rules-based strategies, with optional
role-swapping on failure or per-round rotation.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Assignment, LoopConfig


@dataclass
class AssignmentContext:
    round_index: int
    last_round_failed: bool
    requested_swap: bool


class RoleAssignmentEngine:
    def __init__(self, loop_cfg: LoopConfig) -> None:
        self.loop_cfg = loop_cfg

    def assign(self, ctx: AssignmentContext) -> Assignment:
        role_cfg = self.loop_cfg.role_assignment
        impl_pool = list(role_cfg.implementers)
        rev_pool = list(role_cfg.reviewers)

        if not impl_pool:
            raise ValueError(f"Loop {self.loop_cfg.loop_id} has no implementers configured")
        if not rev_pool:
            raise ValueError(f"Loop {self.loop_cfg.loop_id} has no reviewers configured")

        swap = False
        if self.loop_cfg.swap_next_round and ctx.round_index > 0:
            swap = True
        if self.loop_cfg.swap_on_failure and ctx.last_round_failed:
            swap = True
        if ctx.requested_swap:
            swap = True

        if swap:
            impl_pool, rev_pool = rev_pool, impl_pool

        strategy = role_cfg.strategy.lower()
        if strategy == "static":
            impl = impl_pool[: role_cfg.implementer_count]
            rev = rev_pool[: role_cfg.reviewer_count]
            return Assignment(implementers=impl, reviewers=rev)

        if strategy == "round_robin":
            impl = self._round_robin_pick(
                impl_pool, role_cfg.implementer_count, ctx.round_index
            )
            rev = self._round_robin_pick(rev_pool, role_cfg.reviewer_count, ctx.round_index)
            return Assignment(implementers=impl, reviewers=rev)

        if strategy == "rules_based":
            if ctx.last_round_failed:
                impl = self._round_robin_pick(
                    impl_pool, role_cfg.implementer_count, ctx.round_index + 1
                )
                rev = self._round_robin_pick(rev_pool, role_cfg.reviewer_count, ctx.round_index)
                return Assignment(implementers=impl, reviewers=rev)
            impl = self._round_robin_pick(
                impl_pool, role_cfg.implementer_count, ctx.round_index
            )
            rev = self._round_robin_pick(rev_pool, role_cfg.reviewer_count, ctx.round_index)
            return Assignment(implementers=impl, reviewers=rev)

        raise ValueError(f"Unsupported role assignment strategy: {strategy}")

    @staticmethod
    def _round_robin_pick(pool: list[str], count: int, round_index: int) -> list[str]:
        if count <= 0:
            return []
        picks: list[str] = []
        for offset in range(count):
            idx = (round_index + offset) % len(pool)
            picks.append(pool[idx])
        return picks
