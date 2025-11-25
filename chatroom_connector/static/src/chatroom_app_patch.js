import {ChatroomApp} from "@chatroom/components/chatroom_app/chatroom_app";
import {patch} from "@web/core/utils/patch";
import {user} from "@web/core/user";

patch(ChatroomApp.prototype, {
    async loadChats() {
        const rooms = await this.orm.call("chatroom.room", "search_read", [], {
            domain: [["state", "!=", "closed"]],
            fields: [
                "name",
                "connector_id",
                "assigned_to_id",
                "state",
                "message_count",
                "last_message_date",
                "last_message_preview",
                "partner_ids",
            ],
            order: "last_message_date desc",
        });

        if (this.state.isManager) {
            this.state.myChats = rooms.filter((r) => r.assigned_to_id);
        } else {
            this.state.myChats = rooms.filter(
                (r) => r.assigned_to_id && r.assigned_to_id[0] === user.userId
            );
        }

        this.state.unassignedChats = rooms.filter((r) => !r.assigned_to_id);
    },
});
