"""
Tests for shielding functionality.
"""

import anyio
import pytest

from hother.cancelable import Cancelable, OperationStatus


class TestShielding:
    """Test shielding from cancelation."""

    @pytest.mark.anyio
    async def test_shield_basic(self):
        """Test basic shielding from cancelation."""
        completed_steps = []

        try:
            async with Cancelable.with_timeout(0.1) as parent:
                completed_steps.append("parent_start")

                # This will complete despite parent timeout
                async with parent.shield():
                    completed_steps.append("shield_start")
                    await anyio.sleep(0.2)  # Longer than parent timeout
                    completed_steps.append("shield_end")

                # This won't execute due to timeout
                completed_steps.append("parent_end")
        except anyio.get_cancelled_exc_class():
            # Expected cancelation
            pass

        assert completed_steps == ["parent_start", "shield_start", "shield_end"]

    @pytest.mark.anyio
    async def test_nested_shields(self):
        """Test nested shielding."""
        execution_order = []

        try:
            async with Cancelable.with_timeout(0.1) as parent:
                execution_order.append("parent_start")

                async with parent.shield() as shield1:
                    execution_order.append("shield1_start")

                    async with shield1.shield():
                        execution_order.append("shield2_start")
                        await anyio.sleep(0.15)
                        execution_order.append("shield2_end")

                    execution_order.append("shield1_end")

                execution_order.append("parent_end")
        except anyio.get_cancelled_exc_class():
            # Expected cancelation after shields complete
            pass

        # All shielded sections should complete
        assert execution_order == ["parent_start", "shield1_start", "shield2_start", "shield2_end", "shield1_end"]

    @pytest.mark.anyio
    async def test_shield_status(self):
        """Test shield status tracking."""
        async with Cancelable() as parent:
            async with parent.shield() as shielded:
                assert shielded.context.status == OperationStatus.SHIELDED
                assert shielded.context.metadata.get("shielded") is True
                assert shielded.context.parent_id == parent.context.id

    @pytest.mark.anyio
    async def test_shield_with_manual_cancelation(self):
        """Test shielding with manual cancelation."""
        completed = []

        try:
            async with Cancelable(name="parent") as parent:
                completed.append("parent_start")

                async with parent.shield():
                    completed.append("shield_start")

                    # Cancel parent while in shield
                    await parent.cancel()

                    # Shield should still complete
                    await anyio.sleep(0.1)
                    completed.append("shield_end")

                # This should not execute
                completed.append("parent_end")
        except anyio.get_cancelled_exc_class():
            pass

        assert completed == ["parent_start", "shield_start", "shield_end"]

    @pytest.mark.anyio
    async def test_shield_cancelation_propagation(self):
        """Test that cancelation doesn't propagate through shield."""
        # This test verifies that the shield properly isolates its content
        # from cancelation but allows the parent to be cancelled afterward

        shield_completed = False
        parent_after_shield = False

        async def shielded_operation(parent):
            nonlocal shield_completed
            async with parent.shield():
                await anyio.sleep(0.15)  # Longer than parent timeout
                shield_completed = True

        try:
            async with Cancelable.with_timeout(0.1) as parent:
                await shielded_operation(parent)
                parent_after_shield = True
        except anyio.get_cancelled_exc_class():
            # Expected - parent times out after shield completes
            pass

        assert shield_completed  # Shield should complete
        assert not parent_after_shield  # Parent should be cancelled after shield
