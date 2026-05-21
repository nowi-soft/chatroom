def post_init_hook(env):
    env["chatroom.ai.provider"].sudo()._ensure_management_setup()
