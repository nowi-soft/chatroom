import {ChatroomApp} from "@chatroom/components/chatroom_app/chatroom_app";
import {onMounted} from "@odoo/owl";
import {patch} from "@web/core/utils/patch";

patch(ChatroomApp.prototype, {
    getChatItemClass(chat) {
        return {
            active: this.state.currentRoom?.id === chat.id,
            "ai-active": chat.ai_enabled,
            "needs-attention": chat.needs_attention,
        };
    },

    setup() {
        super.setup(...arguments);

        onMounted(async () => {
            await this._loadAIFields();
        });

        this.busService.subscribe(
            "chatroom/ai_intervention_needed",
            this.onAIInterventionNeeded.bind(this)
        );

        this.busService.subscribe(
            "chatroom/ai_state_changed",
            this.onAIStateChanged.bind(this)
        );
    },

    async _loadAIFields() {
        const allChats = [...this.state.myChats, ...this.state.unassignedChats];
        if (allChats.length === 0) return;

        const chatIds = allChats.map((c) => c.id);
        const aiData = await this.orm.searchRead(
            "chatroom.room",
            [["id", "in", chatIds]],
            [
                "id",
                "ai_enabled",
                "ai_agent_id",
                "ai_conversation_state",
                "needs_attention",
            ]
        );

        const aiMap = {};
        aiData.forEach((d) => {
            aiMap[d.id] = d;
        });

        this.state.myChats = this.state.myChats.map((chat) => {
            const ai = aiMap[chat.id];
            if (ai) {
                return {...chat, ...ai};
            }
            return chat;
        });

        this.state.unassignedChats = this.state.unassignedChats.map((chat) => {
            const ai = aiMap[chat.id];
            if (ai) {
                return {...chat, ...ai};
            }
            return chat;
        });
    },

    async onAIStateChanged(payload) {
        const {room_id, ai_enabled} = payload;

        const myChat = this.state.myChats.find((c) => c.id === room_id);
        if (myChat) {
            myChat.ai_enabled = ai_enabled;
        }

        const unassignedChat = this.state.unassignedChats.find((c) => c.id === room_id);
        if (unassignedChat) {
            unassignedChat.ai_enabled = ai_enabled;
        }

        if (this.state.currentRoom?.id === room_id) {
            this.state.currentRoom.ai_enabled = ai_enabled;
        }
    },

    async loadMessages(roomId) {
        if (this.__owl__.status === 5) {
            return;
        }

        try {
            await super.loadMessages(roomId);
        } catch (error) {
            if (error.message !== "Component is destroyed") {
                console.error("Error loading messages:", error);
            }
        }
    },

    async onMessageCreated(payload) {
        if (this.__owl__.status === 5) {
            return;
        }

        try {
            await super.onMessageCreated(payload);
        } catch (error) {
            if (error.message !== "Component is destroyed") {
                console.error("Error on message created:", error);
            }
        }
    },

    async selectChat() {
        await super.selectChat(...arguments);

        await this._reloadCurrentRoomAIFields();
    },

    async restoreRoom() {
        await super.restoreRoom(...arguments);

        await this._reloadCurrentRoomAIFields();
    },

    async _reloadCurrentRoomAIFields() {
        if (!this.state.currentRoom?.id) return;

        const [updatedRoom] = await this.orm.searchRead(
            "chatroom.room",
            [["id", "=", this.state.currentRoom.id]],
            ["ai_enabled", "ai_agent_id", "ai_conversation_state"]
        );

        if (updatedRoom) {
            this.state.currentRoom.ai_enabled = updatedRoom.ai_enabled;
            this.state.currentRoom.ai_agent_id = updatedRoom.ai_agent_id;
            this.state.currentRoom.ai_conversation_state =
                updatedRoom.ai_conversation_state;
        }
    },

    async onAIInterventionNeeded(payload) {
        const {room_id, room_name, agent_name, reason} = payload;

        this.notification.add(
            `AI Agent "${agent_name}" needs human intervention in chat "${room_name}": ${reason}`,
            {
                type: "warning",
                sticky: true,
                buttons: [
                    {
                        name: "Open Chat",
                        primary: true,
                        onClick: async () => {
                            const room = [
                                ...this.state.myChats,
                                ...this.state.unassignedChats,
                            ].find((r) => r.id === room_id);
                            if (room) {
                                await this.selectChat(room);
                            }
                        },
                    },
                ],
            }
        );

        await this.loadChats();
    },

    async toggleAI(room) {
        const currentState = room.ai_enabled;
        const action = currentState ? "action_disable_ai" : "action_enable_ai";
        const message = currentState
            ? "AI Agent disabled for this chat"
            : "AI Agent enabled for this chat";
        const notifType = currentState ? "info" : "success";

        await this.orm.call("chatroom.room", action, [[room.id]]);

        const [updatedRoom] = await this.orm.searchRead(
            "chatroom.room",
            [["id", "=", room.id]],
            ["ai_enabled", "ai_agent_id", "ai_conversation_state"]
        );

        if (updatedRoom) {
            room.ai_enabled = updatedRoom.ai_enabled;
            room.ai_agent_id = updatedRoom.ai_agent_id;
            room.ai_conversation_state = updatedRoom.ai_conversation_state;

            if (this.state.currentRoom?.id === room.id) {
                this.state.currentRoom.ai_enabled = updatedRoom.ai_enabled;
                this.state.currentRoom.ai_agent_id = updatedRoom.ai_agent_id;
                this.state.currentRoom.ai_conversation_state =
                    updatedRoom.ai_conversation_state;
            }
        }

        this.notification.add(message, {type: notifType});
    },

    async loadChats() {
        await super.loadChats(...arguments);

        await this._loadAIFields();
    },

    async onRoomUpdated(payload) {
        try {
            await super.onRoomUpdated(payload);

            const roomId = payload.id;
            const [aiData] = await this.orm.searchRead(
                "chatroom.room",
                [["id", "=", roomId]],
                ["ai_enabled", "ai_agent_id", "ai_conversation_state"]
            );

            if (aiData) {
                const myChat = this.state.myChats.find((c) => c.id === roomId);
                if (myChat) {
                    Object.assign(myChat, aiData);
                }

                const unassignedChat = this.state.unassignedChats.find(
                    (c) => c.id === roomId
                );
                if (unassignedChat) {
                    Object.assign(unassignedChat, aiData);
                }

                if (this.state.currentRoom?.id === roomId) {
                    Object.assign(this.state.currentRoom, aiData);
                }
            }
        } catch {
            // Component might be destroyed, ignore
        }
    },
});
