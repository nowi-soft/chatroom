import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";

export const aiNotificationService = {
    dependencies: ["bus_service", "notification", "action", "orm"],

    start(env, {bus_service, notification, action, orm}) {
        const activeNotifications = new Map();

        bus_service.subscribe("chatroom/ai_urgent_attention", async (payload) => {
            const {room_id, room_name, needs_attention} = payload;

            if (!needs_attention) {
                return;
            }

            try {
                const rooms = await orm.searchRead(
                    "chatroom.room",
                    [["id", "=", room_id]],
                    ["needs_attention"]
                );

                if (!rooms.length || !rooms[0].needs_attention) {
                    return;
                }
            } catch (error) {
                console.warn("Could not verify room needs_attention status", error);
            }

            if (activeNotifications.has(room_id)) {
                const existingNotif = document.querySelector(
                    `.o_notification.chatroom-urgent-${room_id}`
                );
                if (existingNotif) {
                    existingNotif.querySelector(".o_notification_close")?.click();
                }
                activeNotifications.delete(room_id);
            }

            notification.add(
                _t(
                    "⚠️ Chat '%s' needs urgent attention - AI response failed",
                    room_name
                ),
                {
                    type: "danger",
                    sticky: true,
                    className: `chatroom-urgent-${room_id}`,
                    buttons: [
                        {
                            name: _t("Open Chat"),
                            primary: true,
                            onClick: async () => {
                                activeNotifications.delete(room_id);
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
                    onClose: () => {
                        activeNotifications.delete(room_id);
                    },
                }
            );

            activeNotifications.set(room_id, true);
        });

        bus_service.subscribe("chatroom/room_updated", async (payload) => {
            const {id, needs_attention} = payload;
            if (!needs_attention && activeNotifications.has(id)) {
                const notifElement = document.querySelector(
                    `.o_notification.chatroom-urgent-${id}`
                );
                if (notifElement) {
                    notifElement.querySelector(".o_notification_close")?.click();
                }
                activeNotifications.delete(id);
            }
        });
    },
};

registry.category("services").add("ai_notification_service", aiNotificationService);
