import { patch } from '@web/core/utils/patch';
import { ChatComposer } from '@muk_ai/chat/composer/chat_composer';

const SPREADSHEET_ACCEPT = [
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-excel',
    '.xlsx', '.xls',
].join(',');

patch(ChatComposer.prototype, {
    setup() {
        super.setup();
        this.accept += ',' + SPREADSHEET_ACCEPT;
    },
});
