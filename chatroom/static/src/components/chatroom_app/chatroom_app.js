import {Component, markup, onWillStart, useRef, useState} from "@odoo/owl";
import {Layout} from "@web/search/layout";
import {RecordList} from "../record_list/record_list";
import {registry} from "@web/core/registry";
import {router} from "@web/core/browser/router";
import {useService} from "@web/core/utils/hooks";
import {user} from "@web/core/user";

export class ChatroomApp extends Component {
    static template = "chatroom.ChatroomApp";
    static components = {Layout, RecordList};
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        this.busService = useService("bus_service");
        this.fileInputRef = useRef("fileInput");

        this.mediaRecorder = null;
        this.audioChunks = [];

        this.state = useState({
            myChats: [],
            unassignedChats: [],
            closedChats: [],
            currentRoom: null,
            messages: [],
            loading: false,
            messageInput: "",
            rightPanelTab: "quick_messages",
            isManager: false,
            rightPanelWidth: 400,
            isResizing: false,
            availableTabs: [],
            relatedRecords: [],
            showRelationsMenu: false,
            linkContactMode: false,
            linkedContactIds: [],
            searchQuery: "",
            showClosedChats: false,
            isRecordingAudio: false,
            imageModalUrl: null,
            imageModalAlt: null,
            quickMessages: [],
            previewModal: {
                show: false,
                file: null,
                type: null,
                url: null,
            },
        });

        this.onMessageCreatedBound = this.onMessageCreated.bind(this);
        this.onRoomUpdatedBound = this.onRoomUpdated.bind(this);

        this.busService.subscribe(
            "chatroom/message_created",
            this.onMessageCreatedBound
        );
        this.busService.subscribe("chatroom/room_updated", this.onRoomUpdatedBound);

        onWillStart(async () => {
            const hasGroup = await this.orm.call("res.users", "has_group", [
                user.userId,
                "chatroom.group_chatroom_manager",
            ]);
            this.state.isManager = hasGroup;

            this.state.availableTabs = this.getAvailableTabs();

            await this.loadChats();
            await this.loadQuickMessages();

            if (this.props.action?.params?.partner_id) {
                await this.filterByPartner(this.props.action.params.partner_id);
            } else if (router.current.room_id) {
                await this.restoreRoom(parseInt(router.current.room_id, 10));
            } else if (this.props.action?.params?.room_id) {
                await this.restoreRoom(this.props.action.params.room_id);
            }
        });
    }

    willUnmount() {
        this.busService.unsubscribe(
            "chatroom/message_created",
            this.onMessageCreatedBound
        );
        this.busService.unsubscribe("chatroom/room_updated", this.onRoomUpdatedBound);
    }

    async loadChats() {
        const rooms = await this.orm.call("chatroom.room", "search_read", [], {
            domain: [["state", "!=", "closed"]],
            fields: [
                "name",
                "assigned_to_id",
                "state",
                "needs_attention",
                "message_count",
                "last_message_date",
                "last_message_preview",
                "partner_ids",
            ],
            order: "needs_attention desc, last_message_date desc",
        });

        if (this.state.isManager) {
            this.state.myChats = rooms.filter((r) => r.assigned_to_id);
        } else {
            this.state.myChats = rooms.filter(
                (r) => r.assigned_to_id && r.assigned_to_id[0] === user.userId
            );
        }

        this.state.unassignedChats = rooms.filter((r) => !r.assigned_to_id);
    }

    async loadClosedChats() {
        const rooms = await this.orm.call("chatroom.room", "search_read", [], {
            domain: [["state", "=", "closed"]],
            fields: [
                "name",
                "assigned_to_id",
                "state",
                "message_count",
                "last_message_date",
                "last_message_preview",
                "partner_ids",
            ],
            order: "last_message_date desc",
            limit: 100,
        });
        this.state.closedChats = rooms;
    }

    async loadMessages(roomId) {
        const messages = await this.orm.searchRead(
            "chatroom.message",
            [["room_id", "=", roomId]],
            [
                "body",
                "direction",
                "author_name",
                "message_type",
                "create_date",
                "is_internal",
                "filename",
                "mime_type",
                "file_url",
                "attachment_id",
            ],
            {order: "create_date asc"}
        );

        this.state.messages = messages.map((msg) => ({
            ...msg,
            body: markup(msg.body),
        }));
    }

    selectRightPanelTab(tab) {
        this.state.rightPanelTab = tab;
    }

    openContactsList() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Contacts",
            res_model: "res.partner",
            views: [
                [false, "list"],
                [false, "form"],
            ],
            target: "current",
        });
    }

    async selectChat(room) {
        this.state.currentRoom = room;
        await this.loadMessages(room.id);
        await this.loadRelatedRecords(room.id);

        router.pushState({room_id: room.id});

        setTimeout(() => {
            this.scrollToBottom();
        }, 100);
    }

    async restoreRoom(roomId) {
        try {
            let room = [...this.state.myChats, ...this.state.unassignedChats].find(
                (r) => r.id === roomId
            );

            if (!room) {
                await this.loadClosedChats();
                room = this.state.closedChats.find((r) => r.id === roomId);
            }

            if (room) {
                this.state.currentRoom = room;
                await this.loadMessages(room.id);
                await this.loadRelatedRecords(room.id);
                setTimeout(() => {
                    this.scrollToBottom();
                }, 100);
            }
        } catch (e) {
            console.error("Error restoring room:", e);
        }
    }

    scrollToBottom() {
        const messagesList = document.querySelector(".messages-list");
        if (messagesList) {
            messagesList.scrollTop = messagesList.scrollHeight;
        }
    }

    async loadRelatedRecords(roomId) {
        const result = await this.orm.call("chatroom.room", "get_related_records", [
            [roomId],
        ]);
        this.state.relatedRecords = result || [];

        await this.loadLinkedContactIds(roomId);
    }

    async loadLinkedContactIds(roomId) {
        if (!roomId) {
            this.state.linkedContactIds = [];
            return;
        }

        try {
            const room = await this.orm.read(
                "chatroom.room",
                [roomId],
                ["partner_ids"]
            );
            this.state.linkedContactIds = room[0]?.partner_ids || [];
        } catch (error) {
            console.error("Error loading linked contacts:", error);
            this.state.linkedContactIds = [];
        }
    }

    async createPartnerFromChat() {
        if (!this.state.currentRoom) return;

        const currentRoomId = this.state.currentRoom.id;

        await this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "res.partner",
                view_mode: "form",
                views: [[false, "form"]],
                target: "new",
                context: {
                    default_name: this.state.currentRoom.name,
                    default_chatroom_room_id: currentRoomId,
                },
            },
            {
                onClose: async () => {
                    await this.loadRelatedRecords(currentRoomId);

                    if (this.state.rightPanelTab === "contacts") {
                        const currentTab = this.state.rightPanelTab;
                        this.state.rightPanelTab = null;
                        await new Promise((resolve) => setTimeout(resolve, 10));
                        this.state.rightPanelTab = currentTab;
                    }
                },
            }
        );
    }

    async linkRecordToChat(model, recordId) {
        if (!this.state.currentRoom) return;

        const tab = this.state.availableTabs.find((t) => t.model === model);
        if (!tab || !tab.relationField) {
            this.notification.add("Cannot link this record type", {type: "warning"});
            return;
        }

        if (tab.relationField.endsWith("_ids")) {
            await this.orm.write("chatroom.room", [this.state.currentRoom.id], {
                [tab.relationField]: [[4, recordId]],
            });
        } else {
            await this.orm.write("chatroom.room", [this.state.currentRoom.id], {
                [tab.relationField]: recordId,
            });
        }

        await this.loadRelatedRecords(this.state.currentRoom.id);

        this.state.linkContactMode = false;

        this.notification.add("Contact linked successfully", {type: "success"});
    }

    async unlinkRecord(model, recordId, fieldName) {
        if (!this.state.currentRoom) return;

        if (fieldName.endsWith("_ids")) {
            await this.orm.write("chatroom.room", [this.state.currentRoom.id], {
                [fieldName]: [[3, recordId]],
            });
        } else {
            await this.orm.write("chatroom.room", [this.state.currentRoom.id], {
                [fieldName]: false,
            });
        }

        await this.loadRelatedRecords(this.state.currentRoom.id);
        this.notification.add("Record unlinked", {type: "info"});
    }

    async openRelatedRecord(model, recordId) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: model,
            res_id: recordId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async shareChatLink() {
        if (!this.state.currentRoom) return;

        const records = await this.orm.searchRead(
            "ir.model.data",
            [
                ["module", "=", "chatroom"],
                ["name", "=", "action_chatroom_app"],
            ],
            ["res_id"]
        );

        if (!records.length) {
            this.notification.add("Could not find action", {type: "warning"});
            return;
        }

        const actionId = records[0].res_id;

        const baseUrl = window.location.origin;

        const shareUrl = `${baseUrl}/web#menu_id=&action=${actionId}&room_id=${this.state.currentRoom.id}`;

        try {
            await navigator.clipboard.writeText(shareUrl);
            this.notification.add("Link copied to clipboard!", {type: "success"});
        } catch (err) {
            console.warn("Clipboard API call failed", err);
            const textArea = document.createElement("textarea");
            textArea.value = shareUrl;
            textArea.style.position = "fixed";
            textArea.style.left = "-999999px";
            document.body.appendChild(textArea);
            textArea.select();
            try {
                document.execCommand("copy");
                this.notification.add("Link copied to clipboard!", {type: "success"});
            } catch (copyError) {
                console.warn("Fallback clipboard copy failed", copyError);
                this.notification.add("Could not copy link", {type: "warning"});
            }
            document.body.removeChild(textArea);
        }
    }

    toggleRelationsMenu() {
        this.state.showRelationsMenu = !this.state.showRelationsMenu;
    }

    showLinkContactMode() {
        this.state.linkContactMode = true;
        this.state.rightPanelTab = "contacts";
        this.notification.add("Select a contact from the list (simple click to link)", {
            type: "info",
            sticky: true,
        });
    }

    async assignToMe(roomId) {
        await this.orm.call("chatroom.room", "action_assign_to_me", [[roomId]]);
        await this.loadChats();
        this.notification.add("Chat assigned to you", {type: "success"});
    }

    async unassignChat(roomId) {
        await this.orm.call("chatroom.room", "action_unassign", [[roomId]]);

        if (this.state.currentRoom?.id === roomId) {
            this.state.currentRoom = null;
            this.state.messages = [];
        }

        this.notification.add("Chat unassigned", {type: "info"});
    }

    async closeChat(roomId) {
        await this.orm.call("chatroom.room", "action_close", [[roomId]]);

        if (this.state.currentRoom?.id === roomId) {
            this.state.currentRoom = null;
            this.state.messages = [];
        }

        this.notification.add("Chat closed", {type: "info"});
    }

    async reopenChatAssigned(roomId) {
        await this.orm.write("chatroom.room", [roomId], {
            state: "assigned",
            assigned_to_id: user.userId,
        });

        await this.orm.call("chatroom.room", "notify_room_updated", [[roomId]]);
        await this.loadChats();
        this.notification.add("Chat reopened and assigned to you", {type: "success"});
    }

    async reopenChatUnassigned(roomId) {
        await this.orm.write("chatroom.room", [roomId], {
            state: "unassigned",
            assigned_to_id: false,
        });

        await this.orm.call("chatroom.room", "notify_room_updated", [[roomId]]);
        await this.loadChats();
        this.notification.add("Chat reopened as unassigned", {type: "success"});
    }

    toggleClosedChats() {
        this.state.showClosedChats = !this.state.showClosedChats;
        if (this.state.showClosedChats) {
            this.loadClosedChats();
        }
    }

    get filteredClosedChats() {
        if (!this.state.searchQuery) {
            return this.state.closedChats;
        }
        const query = this.state.searchQuery.toLowerCase();
        return this.state.closedChats.filter(
            (chat) =>
                chat.name.toLowerCase().includes(query) ||
                (chat.last_message_preview &&
                    chat.last_message_preview.toLowerCase().includes(query))
        );
    }

    async sendMessage() {
        if (!this.state.messageInput.trim() || !this.state.currentRoom) {
            return;
        }

        await this.orm.create("chatroom.message", [
            {
                room_id: this.state.currentRoom.id,
                body: this.state.messageInput,
                direction: "outgoing",
            },
        ]);

        this.state.messageInput = "";
        await this.loadMessages(this.state.currentRoom.id);

        setTimeout(() => {
            this.scrollToBottom();
        }, 100);
    }

    async addInternalNote() {
        if (!this.state.messageInput.trim() || !this.state.currentRoom) {
            return;
        }

        await this.orm.create("chatroom.message", [
            {
                room_id: this.state.currentRoom.id,
                body: this.state.messageInput,
                direction: "outgoing",
                is_internal: true,
            },
        ]);

        this.state.messageInput = "";
        await this.loadMessages(this.state.currentRoom.id);
        this.notification.add("Internal note added", {type: "success"});

        setTimeout(() => {
            this.scrollToBottom();
        }, 100);
    }

    async onFileSelected(ev) {
        const files = ev.target.files;
        if (!files || files.length === 0 || !this.state.currentRoom) {
            return;
        }

        for (const file of files) {
            const messageType = file.type.startsWith("image/")
                ? "image"
                : file.type.startsWith("audio/")
                  ? "audio"
                  : "file";
            this.openPreviewModal(file, messageType);
        }

        ev.target.value = "";
    }

    async startRecordingAudio() {
        if (!this.state.currentRoom) {
            return;
        }

        try {
            const stream = await navigator.mediaDevices.getUserMedia({audio: true});
            this.mediaRecorder = new MediaRecorder(stream);
            this.audioChunks = [];

            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                }
            };

            this.mediaRecorder.onstop = async () => {
                const audioBlob = new Blob(this.audioChunks, {
                    type: "audio/ogg; codecs=opus",
                });
                const audioFile = new File([audioBlob], `audio_${Date.now()}.ogg`, {
                    type: "audio/ogg",
                });

                stream.getTracks().forEach((track) => track.stop());

                this.openPreviewModal(audioFile, "audio");
            };

            this.mediaRecorder.start();
            this.state.isRecordingAudio = true;
        } catch (error) {
            console.error("Error accessing microphone:", error);
            this.notification.add("No se pudo acceder al micrófono", {type: "danger"});
        }
    }

    stopRecordingAudio() {
        if (this.mediaRecorder && this.state.isRecordingAudio) {
            this.mediaRecorder.stop();
            this.state.isRecordingAudio = false;
        }
    }

    toggleAudioRecording() {
        if (this.state.isRecordingAudio) {
            this.stopRecordingAudio();
        } else {
            this.startRecordingAudio();
        }
    }

    async uploadFile(file, messageType, isInternal = false) {
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

            let finalMessageType = messageType;
            if (messageType === "file") {
                if (file.type.startsWith("image/")) {
                    finalMessageType = "image";
                } else if (file.type.startsWith("audio/")) {
                    finalMessageType = "audio";
                }
            }
            await this.orm.create("chatroom.message", [
                {
                    room_id: this.state.currentRoom.id,
                    body: this.state.messageInput || "",
                    direction: "outgoing",
                    message_type: finalMessageType,
                    attachment_id: attachmentId,
                    filename: file.name,
                    mime_type: file.type,
                    is_internal: isInternal,
                },
            ]);

            this.state.messageInput = "";
            await this.loadMessages(this.state.currentRoom.id);

            if (isInternal) {
                this.notification.add("File saved as internal note", {
                    type: "success",
                });
            } else {
                this.notification.add(
                    `${finalMessageType === "audio" ? "Audio" : "File"} sent successfully`,
                    {
                        type: "success",
                    }
                );
            }

            setTimeout(() => {
                this.scrollToBottom();
            }, 100);
        } catch (error) {
            console.error("Error uploading file:", error);
            this.notification.add("Failed to upload file", {type: "danger"});
        }
    }

    onMessageInputKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.sendMessage();
        }
    }

    openImageModal(imageUrl, imageAlt) {
        this.state.imageModalUrl = imageUrl;
        this.state.imageModalAlt = imageAlt || "Image";
    }

    closeImageModal() {
        this.state.imageModalUrl = null;
        this.state.imageModalAlt = null;
    }

    openPreviewModal(file, type) {
        const url = URL.createObjectURL(file);
        this.state.previewModal = {
            show: true,
            file: file,
            type: type,
            url: url,
        };
    }

    closePreviewModal() {
        if (this.state.previewModal.url) {
            URL.revokeObjectURL(this.state.previewModal.url);
        }
        this.state.previewModal = {
            show: false,
            file: null,
            type: null,
            url: null,
        };
    }

    async confirmSendFile() {
        const {file, type} = this.state.previewModal;
        this.closePreviewModal();
        // Map type to messageType for uploadFile
        const messageType =
            type === "audio" ? "audio" : type === "image" ? "image" : "file";
        await this.uploadFile(file, messageType);
    }

    async confirmSendFileAsNote() {
        const {file, type} = this.state.previewModal;
        this.closePreviewModal();
        // Map type to messageType for uploadFile
        const messageType =
            type === "audio" ? "audio" : type === "image" ? "image" : "file";
        await this.uploadFile(file, messageType, true);
    }

    getAvailableTabs() {
        return [
            {
                id: "quick_messages",
                name: "Quick Messages",
                singular: "Quick Message",
                icon: "fa-comments",
            },
            {
                id: "contacts",
                name: "Contacts",
                singular: "Contact",
                icon: "fa-address-book",
                model: "res.partner",
                relationField: "partner_ids",
                fields: ["name", "email", "phone", "image_128"],
                searchField: "name",

                getDropText: (record) => {
                    const lines = [];
                    if (record.name) lines.push(record.name);
                    if (record.phone) lines.push(record.phone);
                    if (record.email) lines.push(record.email);
                    return lines.join("\n");
                },
            },
        ];
    }

    async loadTabData(tab) {
        if (!tab.model) return [];

        const records = await this.orm.searchRead(
            tab.model,
            [],
            tab.fields || ["name"],
            {limit: 50, order: "id desc"}
        );
        return records;
    }

    async loadQuickMessages() {
        this.state.quickMessages = await this.orm.call(
            "chatroom.quick.message",
            "search_read",
            [],
            {
                domain: [["active", "=", true]],
                fields: ["name", "message", "sequence"],
                order: "sequence, name",
            }
        );
    }

    async sendQuickMessage(message) {
        if (!this.state.currentRoom) {
            this.notification.add("Please select a chat first", {type: "warning"});
            return;
        }

        await this.orm.create("chatroom.message", [
            {
                room_id: this.state.currentRoom.id,
                body: message,
                direction: "outgoing",
            },
        ]);

        await this.loadMessages(this.state.currentRoom.id);
        this.notification.add("Quick message sent", {type: "success"});

        setTimeout(() => {
            this.scrollToBottom();
        }, 100);
    }

    copyQuickMessageToInput(message) {
        this.state.messageInput = message;
        this.notification.add("Message copied to input", {type: "info"});
    }

    showLinkMode() {
        const currentTab = this.state.availableTabs.find(
            (t) => t.id === this.state.rightPanelTab
        );
        if (!currentTab) return;

        if (currentTab.id === "contacts") {
            this.state.linkContactMode = true;
            this.notification.add("Select a contact to link to this chat", {
                type: "info",
            });
        } else if (currentTab.id === "leads") {
            this.state.linkLeadMode = true;
            this.notification.add("Select a lead to link to this chat", {type: "info"});
        }
    }

    async openRecord(model, recordId) {
        await this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: model,
                res_id: recordId,
                views: [[false, "form"]],
                target: "new",
            },
            {
                onClose: async () => {
                    if (this.state.currentRoom) {
                        await this.loadRelatedRecords(this.state.currentRoom.id);
                    }
                },
            }
        );
    }

    async openRecordFullScreen(model, recordId) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: model,
            res_id: recordId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    startResize(ev) {
        this.state.isResizing = true;
        this.resizeStartX = ev.clientX;
        this.resizeStartWidth = this.state.rightPanelWidth;

        const onMouseMove = (e) => {
            if (this.state.isResizing) {
                const delta = this.resizeStartX - e.clientX;
                const newWidth = Math.max(
                    300,
                    Math.min(800, this.resizeStartWidth + delta)
                );
                this.state.rightPanelWidth = newWidth;
            }
        };

        const onMouseUp = () => {
            this.state.isResizing = false;
            document.removeEventListener("mousemove", onMouseMove);
            document.removeEventListener("mouseup", onMouseUp);
        };

        document.addEventListener("mousemove", onMouseMove);
        document.addEventListener("mouseup", onMouseUp);
    }

    async filterByPartner(partnerId) {
        const filteredChats = [
            ...this.state.myChats,
            ...this.state.unassignedChats,
        ].filter((chat) => chat.partner_ids && chat.partner_ids.includes(partnerId));

        if (filteredChats.length > 0) {
            await this.selectChat(filteredChats[0]);
        }
    }

    onDragOverMessage(ev) {
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "copy";
    }

    onDropToMessage(ev) {
        ev.preventDefault();

        try {
            const recordData = ev.dataTransfer.getData("application/x-odoo-record");
            let textToInsert = "";

            if (recordData) {
                const payload = JSON.parse(recordData);
                textToInsert = payload.text || "";
            } else {
                textToInsert = ev.dataTransfer.getData("text/plain") || "";
            }

            if (textToInsert) {
                let textarea = ev.target;
                if (textarea.tagName !== "TEXTAREA") {
                    textarea = document.querySelector(".messages-input textarea");
                }

                if (!textarea) return;

                const start = textarea.selectionStart || 0;
                const end = textarea.selectionEnd || 0;
                const currentValue = this.state.messageInput || "";

                const newValue =
                    currentValue.substring(0, start) +
                    textToInsert +
                    currentValue.substring(end);
                this.state.messageInput = newValue;

                setTimeout(() => {
                    textarea.selectionStart = textarea.selectionEnd =
                        start + textToInsert.length;
                    textarea.focus();
                }, 0);
            }
        } catch (e) {
            console.error("Error handling drop:", e);
        }
    }

    async onMessageCreated(payload) {
        try {
            const {room_id} = payload;

            if (this.state?.currentRoom && this.state.currentRoom.id === room_id) {
                await this.loadMessages(room_id);

                requestAnimationFrame(() => {
                    requestAnimationFrame(() => {
                        this.scrollToBottom();
                    });
                });
            }
        } catch {
            // Component might be destroyed, ignore
        }
    }

    // eslint-disable-next-line complexity
    onRoomUpdated(payload) {
        try {
            const {
                id,
                name,
                assigned_to_id,
                state,
                needs_attention,
                message_count,
                last_message_date,
                last_message_preview,
            } = payload;

            const userId = user.userId;
            const isManager = this.state.isManager;

            const isClosed = state === "closed";
            const shouldBeInMyChats =
                !isClosed &&
                assigned_to_id &&
                (isManager || assigned_to_id[0] === userId);
            const shouldBeInUnassigned = !isClosed && !assigned_to_id;

            const myChatIndex = this.state.myChats.findIndex((r) => r.id === id);
            const unassignedIndex = this.state.unassignedChats.findIndex(
                (r) => r.id === id
            );
            const closedIndex = this.state.closedChats.findIndex((r) => r.id === id);

            if (myChatIndex !== -1) {
                this.state.myChats.splice(myChatIndex, 1);
            }
            if (unassignedIndex !== -1) {
                this.state.unassignedChats.splice(unassignedIndex, 1);
            }
            if (closedIndex !== -1) {
                this.state.closedChats.splice(closedIndex, 1);
            }

            const roomData = {
                id,
                name,
                assigned_to_id: assigned_to_id || false,
                state,
                needs_attention: needs_attention || false,
                message_count,
                last_message_date,
                last_message_preview,
            };

            if (isClosed) {
                this.state.closedChats.unshift(roomData);

                this.state.closedChats.sort((a, b) => {
                    if (!a.last_message_date) return 1;
                    if (!b.last_message_date) return -1;
                    return (
                        new Date(b.last_message_date) - new Date(a.last_message_date)
                    );
                });
            } else if (shouldBeInMyChats) {
                this.state.myChats.unshift(roomData);

                this.state.myChats.sort((a, b) => {
                    if (!a.last_message_date) return 1;
                    if (!b.last_message_date) return -1;
                    return (
                        new Date(b.last_message_date) - new Date(a.last_message_date)
                    );
                });
            } else if (shouldBeInUnassigned) {
                this.state.unassignedChats.unshift(roomData);

                this.state.unassignedChats.sort((a, b) => {
                    if (!a.last_message_date) return 1;
                    if (!b.last_message_date) return -1;
                    return (
                        new Date(b.last_message_date) - new Date(a.last_message_date)
                    );
                });
            }

            if (this.state?.currentRoom && this.state.currentRoom.id === id) {
                Object.assign(this.state.currentRoom, roomData);
            }
        } catch {
            // Component might be destroyed, ignore
        }
    }
}

registry.category("actions").add("chatroom.app", ChatroomApp);
