import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";

export const aiNotificationService = {
    dependencies: ["bus_service", "notification", "action"],

    start(env, {bus_service, notification, action}) {
        bus_service.subscribe("chatroom/ai_urgent_attention", async (payload) => {
            const {room_id, room_name} = payload;

            notification.add(
                _t(
                    "⚠️ Chat '%s' needs urgent attention - AI response failed",
                    room_name
                ),
                {
                    type: "danger",
                    sticky: true,
                    buttons: [
                        {
                            name: _t("Open Chat"),
                            primary: true,
                            onClick: async () => {
                                await action.doAction({
                                    type: "ir.actions.client",
                                    tag: "chatroom.app",
                                    params: {
                                        room_id: room_id,
                                    },
                                });
                            },
                        },
                    ],
                }
            );
        });
    },
};

registry.category("services").add("ai_notification_service", aiNotificationService);
