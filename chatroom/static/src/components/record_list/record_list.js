import {Component, onMounted, onWillStart, useState} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";

export class RecordList extends Component {
    static template = "chatroom.RecordList";
    static props = {
        tab: Object,
        onRecordClick: Function,
        onRecordLink: {type: Function, optional: true},
        onRecordExpand: {type: Function, optional: true},
        onCreateRecord: {type: Function, optional: true},
        onLinkExisting: {type: Function, optional: true},
        linkMode: {type: Boolean, optional: true},
        linkedRecordIds: {type: Array, optional: true},
    };

    setup() {
        this.orm = useService("orm");

        this.state = useState({
            records: [],
            loading: true,
            searchTerm: "",
            showMenu: false,
        });

        onWillStart(async () => {
            await this.loadRecords();
        });

        onMounted(() => {
            this.onClickOutside = (ev) => {
                if (!this.state.showMenu) return;

                const dropdownElem = ev.target.closest(".dropdown");
                if (!dropdownElem && this.state.showMenu) {
                    this.state.showMenu = false;
                }
            };
            document.addEventListener("click", this.onClickOutside, true);
        });
    }

    willUnmount() {
        if (this.onClickOutside) {
            document.removeEventListener("click", this.onClickOutside, true);
        }
    }

    async loadRecords() {
        this.state.loading = true;
        try {
            const domain =
                this.state.searchTerm && this.props.tab.searchField
                    ? [[this.props.tab.searchField, "ilike", this.state.searchTerm]]
                    : [];

            this.state.records = await this.orm.searchRead(
                this.props.tab.model,
                domain,
                this.props.tab.fields || ["name"],
                {limit: 50, order: "id desc"}
            );
        } finally {
            this.state.loading = false;
        }
    }

    async onSearchKeyup() {
        await this.loadRecords();
    }

    async onSearch() {
        await this.loadRecords();
    }

    onRecordClick(record, ev) {
        if (this.props.linkMode && this.props.onRecordLink) {
            this.props.onRecordLink(this.props.tab.model, record.id);
        } else if ((ev.ctrlKey || ev.metaKey) && this.props.onRecordLink) {
            this.props.onRecordLink(this.props.tab.model, record.id);
        } else {
            this.props.onRecordClick(this.props.tab.model, record.id);
        }
    }

    onExpandClick(record) {
        if (this.props.onRecordExpand) {
            this.props.onRecordExpand(this.props.tab.model, record.id);
        }
    }

    getRecordImage(record) {
        if (record.image_128) {
            return `data:image/png;base64,${record.image_128}`;
        }
        return false;
    }

    getRecordTitle(record) {
        return record.name || record.display_name || `ID: ${record.id}`;
    }

    getRecordSubtitle(record) {
        if (record.email) return record.email;
        if (record.phone) return record.phone;
        if (record.default_code) return record.default_code;
        return "";
    }

    toggleMenu() {
        this.state.showMenu = !this.state.showMenu;
    }

    closeMenu() {
        this.state.showMenu = false;
    }

    onCreateRecord() {
        this.closeMenu();
        if (this.props.onCreateRecord) {
            this.props.onCreateRecord();
        }
    }

    onLinkExisting() {
        this.closeMenu();
        if (this.props.onLinkExisting) {
            this.props.onLinkExisting();
        }
    }

    onDragStart(record, ev) {
        try {
            let dropText = this.getRecordTitle(record);
            if (
                this.props.tab.getDropText &&
                typeof this.props.tab.getDropText === "function"
            ) {
                dropText = this.props.tab.getDropText(record);
            }

            const payload = {
                model: this.props.tab.model,
                id: record.id,
                text: dropText,
            };

            ev.dataTransfer.setData(
                "application/x-odoo-record",
                JSON.stringify(payload)
            );

            ev.dataTransfer.setData(
                "text/plain",
                payload.text || this.getRecordTitle(record)
            );
            ev.dataTransfer.effectAllowed = "copy";
        } catch (e) {
            console.error("Error setting drag data:", e);
        }
    }
}
