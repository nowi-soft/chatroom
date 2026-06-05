import {patch} from "@web/core/utils/patch";
import {ChatroomApp} from "@chatroom/components/chatroom_app/chatroom_app";

patch(ChatroomApp.prototype, {
    async _loadRoomAiData(rooms) {
        if (!rooms.length) return;
        const roomIds = rooms.map((r) => r.id);
        const aiData = await this.orm.read("chatroom.room", roomIds, [
            "ai_active",
            "muk_ai_agent_id",
        ]);
        const aiMap = Object.fromEntries(aiData.map((r) => [r.id, r]));
        for (const room of rooms) {
            const data = aiMap[room.id];
            if (data) {
                room.ai_active = data.ai_active;
                room.muk_ai_agent_id = data.muk_ai_agent_id;
            }
        }
    },

    async toggleAiActive(room) {
        const newVal = !room.ai_active;
        await this.orm.write("chatroom.room", [room.id], {ai_active: newVal});
        room.ai_active = newVal;
        if (this.state.currentRoom?.id === room.id) {
            this.state.currentRoom.ai_active = newVal;
        }
        this.notification.add(
            newVal ? "AI activado" : "AI pausado — atención manual",
            {type: "info"}
        );
    },

    onRoomUpdated(payload) {
        super.onRoomUpdated(...arguments);
        const {id, ai_active} = payload;
        if (ai_active === undefined) return;
        for (const list of [
            this.state.myChats,
            this.state.unassignedChats,
            this.state.closedChats,
        ]) {
            const room = list.find((r) => r.id === id);
            if (room) room.ai_active = ai_active;
        }
        if (this.state.currentRoom?.id === id) {
            this.state.currentRoom.ai_active = ai_active;
        }
    },
});
