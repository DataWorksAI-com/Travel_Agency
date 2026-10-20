import os
import unittest
from unittest.mock import AsyncMock, patch

import orchestrator
from desktop.dining_policy import UNAVAILABLE, is_dining_only


class DiningPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_dining_requests_never_call_model_or_sample_agents(self):
        for query in ("Recommend a restaurant in New Hampshire", "给我推荐一个 new hamspire 的餐厅", "Where to eat in Denver?"):
            with self.subTest(query=query), patch.dict(os.environ, {"TRAVEL_STANDALONE": "1"}), patch.object(orchestrator, "get_client") as client:
                self.assertEqual(await orchestrator.plan_trip(query), UNAVAILABLE)
                client.assert_not_called()

    async def test_full_trip_keeps_other_sections_but_blocks_dining_samples(self):
        client = AsyncMock()
        client.call.return_value = "Other section"
        with patch.dict(os.environ, {"TRAVEL_STANDALONE": "1"}), patch.object(orchestrator, "get_client", return_value=client) as factory:
            result = await orchestrator._run_parallel_subagents("Plan a trip to Denver", "")
        self.assertEqual(result["restaurants"], UNAVAILABLE)
        self.assertEqual(result["flights"], "Other section")
        self.assertNotIn(unittest.mock.call("restaurants"), factory.call_args_list)

    def test_trip_with_food_still_runs_trip_flow(self):
        self.assertFalse(is_dining_only("Plan a trip to Denver with restaurants"))
        self.assertFalse(is_dining_only("安排丹佛行程和餐厅"))
        self.assertFalse(is_dining_only("Colorado"))

    async def test_non_standalone_restaurant_integration_is_preserved(self):
        client = AsyncMock()
        client.call.return_value = "Connected data"
        with patch.dict(os.environ, {"TRAVEL_STANDALONE": "0"}), patch.object(orchestrator, "get_client", return_value=client):
            self.assertEqual(await orchestrator.ask_slot("restaurants", "Denver"), "Connected data")


if __name__ == "__main__":
    unittest.main()
