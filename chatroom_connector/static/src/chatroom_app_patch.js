import {ChatroomApp} from "@chatroom/components/chatroom_app/chatroom_app";
import {patch} from "@web/core/utils/patch";

patch(ChatroomApp.prototype, {
    _roomListFields() {
        return [...super._roomListFields(), "connector_id"];
    },
});
