import {markup, onMounted} from "@odoo/owl";

import {ChatroomApp} from "@chatroom/components/chatroom_app/chatroom_app";
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

            // Load AI-specific fields for messages
            if (this.state.messages && this.state.messages.length > 0) {
                const messageIds = this.state.messages.map((m) => m.id);
                const aiMessages = await this.orm.searchRead(
                    "chatroom.message",
                    [["id", "in", messageIds]],
                    [
                        "id",
                        "is_ai_generated",
                        "is_transcribing",
                        "is_transcribed",
                        "is_transcription_failed",
                        "body",
                    ]
                );

                const aiMap = {};
                aiMessages.forEach((msg) => {
                    aiMap[msg.id] = msg;
                });

                this.state.messages = this.state.messages.map((msg) => {
                    const aiData = aiMap[msg.id];
                    if (aiData) {
                        return {
                            ...msg,
                            is_ai_generated: aiData.is_ai_generated,
                            is_transcribing: aiData.is_transcribing,
                            is_transcribed: aiData.is_transcribed,
                            is_transcription_failed: aiData.is_transcription_failed,
                            body: aiData.body ? markup(aiData.body) : msg.body,
                        };
                    }
                    return msg;
                });
            }
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

    async uploadFile(file, messageType) {
        const finalMessageType =
            messageType === "file"
                ? file.type.startsWith("image/")
                    ? "image"
                    : file.type.startsWith("audio/")
                      ? "audio"
                      : "file"
                : messageType;

        if (finalMessageType === "audio") {
            try {
                const formData = new FormData();
                formData.append("files", file);
                formData.append("csrf_token", odoo.csrf_token);

                const uploadResponse = await fetch("/chatroom/upload_file", {
                    method: "POST",
                    body: formData,
                });

                if (!uploadResponse.ok) {
                    throw new Error("File upload failed");
                }

                const uploadResult = await uploadResponse.json();
                const attachmentId = uploadResult.attachments[0].id;

                await this.orm.create("chatroom.message", [
                    {
                        room_id: this.state.currentRoom.id,
                        body: "",
                        direction: "outgoing",
                        message_type: "audio",
                        attachment_id: attachmentId,
                        filename: file.name,
                        mime_type: file.type,
                    },
                ]);

                this.state.messageInput = "";
                await this.loadMessages(this.state.currentRoom.id);

                this.notification.add("Audio sent successfully", {
                    type: "success",
                });

                setTimeout(() => {
                    this.scrollToBottom();
                }, 100);
            } catch (error) {
                console.error("Error uploading audio:", error);
                this.notification.add("Failed to upload audio", {type: "danger"});
            }
        } else {
            await super.uploadFile(file, messageType);
        }
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
