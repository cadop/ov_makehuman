import omni.ext
import omni.ui as ui
import carb
import carb.events
import omni
from functools import partial
import asyncio
import omni.usd
from pxr import Usd
from typing import Union

from .window import MHWindow, WINDOW_TITLE, MENU_PATH

class MakeHumanExtension(omni.ext.IExt):
    # # ext_id is current extension id. It can be used with extension manager to query additional information, like where
    # # this extension is located on filesystem.

    def on_startup(self, ext_id):

        # subscribe to stage events
        # see https://github.com/mtw75/kit_customdata_view
        _usd_context = omni.usd.get_context()
        self._selection = _usd_context.get_selection()
        self._human_selection_event = carb.events.type_from_string("siborg.create.human.human_selected")
        
        # subscribe to stage events
        self._events = _usd_context.get_stage_event_stream()
        self._stage_event_sub = self._events.create_subscription_to_push(
            self._on_stage_event,
            name='human seletion changed',
            )

    #     # get message bus event stream so we can push events to the message bus
        self._bus = omni.kit.app.get_app().get_message_bus_event_stream()

        ui.Workspace.set_show_window_fn(WINDOW_TITLE, partial(self.show_window, None))

        # create a menu item to open the window
        editor_menu = omni.kit.ui.get_editor_menu()
        if editor_menu:
            self._menu = editor_menu.add_item(
                MENU_PATH, self.show_window, toggle=True, value=True
            )
        # show the window
        ui.Workspace.show_window(WINDOW_TITLE)
        print("[siborg.create.human] HumanGeneratorExtension startup")

    def on_shutdown(self):
        self._menu = None
        if self._window:
            self._window.destroy()
            self._window = None

        # Deregister the function that shows the window from omni.ui
        ui.Workspace.set_show_window_fn(WINDOW_TITLE, None)

        # Unsubscribe from stage events
        self._stage_event_sub.unsubscribe()

    async def _destroy_window_async(self):
        # wait one frame, this is due to the one frame defer
        # in Window::_moveToMainOSWindow()
        await omni.kit.app.get_app().next_update_async()
        if self._window:
            self._window.destroy()
            self._window = None

    def visibility_changed(self, visible):
        # Called when window closed by user
        editor_menu = omni.kit.ui.get_editor_menu()
        # Update the menu item to reflect the window state
        if editor_menu:
            editor_menu.set_value(MENU_PATH, visible)
        if not visible:
            # Destroy the window, since we are creating new window
            # in show_window
            asyncio.ensure_future(self._destroy_window_async())

    def show_window(self, menu, value):
        """Handles showing and hiding the window"""
        if value:
            self._window = MHWindow(WINDOW_TITLE)
            # # Dock window wherever the "Content" tab is found (bottom panel by default)
            self._window.deferred_dock_in("Content", ui.DockPolicy.CURRENT_WINDOW_IS_ACTIVE)
            self._window.set_visibility_changed_fn(self.visibility_changed)
        elif self._window:
            self._window.visible = False

    def _on_stage_event(self, event):
        """Handles stage events. This is where we get notified when the user selects/deselects a prim in the viewport."""
        if event.type == int(omni.usd.StageEventType.SELECTION_CHANGED):
            # Get the current selection
            selection = self._selection.get_selected_prim_paths()

            # Check if the selection is empty
            if not selection:
                # Push an event to the message bus with "None" as a payload
                # This event will be picked up by the window and used to update the UI
                carb.log_warn("Human deselected")
                self._bus.push(self._human_selection_event, payload={"prim_path": None})
            else:
                # Get the stage
                _usd_context = omni.usd.get_context()
                stage = _usd_context.get_stage()

                if selection and stage:
                    if len(selection) > 0:
                        path = selection.pop()
                        print(path)
                        prim = stage.GetPrimAtPath(path)
                        prim = self._get_typed_parent(prim, "SkelRoot")
                        # If the selection is a human, push an event to the event stream with the prim as a payload
                        # This event will be picked up by the window and used to update the UI
                        if prim and prim.GetCustomDataByKey("human"):
                            # carb.log_warn("Human selected")
                            path = prim.GetPath().pathString
                            self._bus.push(self._human_selection_event, payload={"prim_path": path})
                        else:
                            # carb.log_warn("Human deselected")
                            self._bus.push(self._human_selection_event, payload={"prim_path": None})

    def _get_typed_parent(self, prim: Union[Usd.Prim, None], type_name: str, level: int = 5):
        """Returns the first parent of the given prim with the given type name. If no parent is found, returns None.

        Parameters:
        -----------
        prim : Usd.Prim or None
            The prim to search from. If None, returns None.
        type_name : str
            The parent type name to search for
        level : int
            The maximum number of levels to traverse. Defaults to 5.

        Returns:
        --------
        Usd.Prim
            The first parent of the given prim with the given type name. If no match is found, returns None.
        """

        if (not prim) or level == 0:
            return None
        elif prim and prim.GetTypeName() == type_name:
            return prim
        else:
            return self._get_typed_parent(prim.GetParent(), type_name, level - 1)
