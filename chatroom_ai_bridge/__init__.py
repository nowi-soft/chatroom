from . import models
from . import mcp


def post_init_hook(env):
    agents = env["muk_ai.agent"].search([("is_customer_facing", "=", True)])
    if agents:
        agents._sync_customer_facing_skills()
