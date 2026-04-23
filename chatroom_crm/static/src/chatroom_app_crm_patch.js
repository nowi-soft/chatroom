import {ChatroomApp} from "@chatroom/components/chatroom_app/chatroom_app";
import {patch} from "@web/core/utils/patch";

patch(ChatroomApp.prototype, {
    setup() {
        super.setup(...arguments);

        Object.assign(this.state, {
            linkLeadMode: false,
            linkedLeadIds: [],
        });
    },

    getAvailableTabs() {
        const tabs = super.getAvailableTabs();

        tabs.push({
            id: "leads",
            name: "Leads",
            singular: "Lead",
            icon: "fa-trophy",
            model: "crm.lead",
            relationField: "related_lead_ids",
            fields: [
                "name",
                "partner_id",
                "contact_name",
                "phone",
                "email_from",
                "stage_id",
                "expected_revenue",
                "priority",
            ],
            searchField: "name",
            domain: [["type", "=", "opportunity"]],
        });

        return tabs;
    },

    async selectChat(room) {
        await super.selectChat(...arguments);
        await this.loadLinkedLeadIds(room?.id);
    },

    async restoreRoom() {
        await super.restoreRoom(...arguments);
        await this.loadLinkedLeadIds(this.state.currentRoom?.id);
    },

    async loadLinkedLeadIds(roomId) {
        if (!roomId) {
            this.state.linkedLeadIds = [];
            return;
        }

        try {
            const room = await this.orm.read(
                "chatroom.room",
                [roomId],
                ["related_lead_ids"]
            );
            this.state.linkedLeadIds = room[0]?.related_lead_ids || [];
        } catch (error) {
            console.error("Error loading linked leads:", error);
            this.state.linkedLeadIds = [];
        }
    },

    async createLeadFromChat() {
        if (!this.state.currentRoom) return;

        const action = await this.orm.call(
            "chatroom.room",
            "action_create_lead_wizard",
            [[this.state.currentRoom.id]]
        );

        if (action) {
            await this.action.doAction(action, {
                onClose: async () => {
                    if (this.state.currentRoom) {
                        await this.loadRelatedRecords(this.state.currentRoom.id);
                    }
                },
            });
        }
    },
});
