# Copyright 2022 the Regents of the University of California, Nerfstudio Team and contributors. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from pathlib import Path

import viser
import viser.transforms as vtf
from typing_extensions import Literal, List

from nerfstudio.data.scene_box import OrientedBox
from nerfstudio.models.base_model import Model
from nerfstudio.models.splatfacto import SplatfactoModel
from nerfstudio.viewer.control_panel import ControlPanel


def populate_export_tab(
    server: viser.ViserServer,
    control_panel: ControlPanel,
    config_path: Path,
    viewer_model: Model,
) -> None:
    viewing_gsplat = isinstance(viewer_model, SplatfactoModel)
    if not viewing_gsplat:
        crop_output = server.add_gui_checkbox("Use Crop", False)

        @crop_output.on_update
        def _(_) -> None:
            control_panel.crop_viewport = crop_output.value

    with server.add_gui_folder("Splat"):
        populate_splat_tab(server, control_panel, config_path, viewing_gsplat)
    with server.add_gui_folder("Point Cloud"):
        populate_point_cloud_tab(server, control_panel, config_path, viewing_gsplat)
    with server.add_gui_folder("Mesh"):
        populate_mesh_tab(server, control_panel, config_path, viewing_gsplat)


def show_command_modal(
    client: viser.ClientHandle,
    what: Literal["mesh", "point cloud", "splat"],
    command: str,
) -> None:
    """Show a modal to each currently connected client.

    In the future, we should only show the modal to the client that pushes the
    generation button.
    """
    with client.add_gui_modal(what.title() + " Export") as modal:
        client.add_gui_markdown(
            "\n".join(
                [
                    f"To export a {what}, run the following from the command line:",
                    "",
                    "```",
                    command,
                    "```",
                ]
            )
        )
        close_button = client.add_gui_button("Close")

        @close_button.on_click
        def _(_) -> None:
            modal.close()


def get_crop_string(obb: OrientedBox, crop_viewport: bool) -> List[str]:
    """Takes in an oriented bounding box and returns a string of the form "--obb_{center,rotation,scale}
    and each arg formatted with spaces around it
    """
    if not crop_viewport:
        return ""
    rpy = vtf.SO3.from_matrix(obb.R.numpy(force=True)).as_rpy_radians()
    pos = obb.T.squeeze().tolist()
    scale = obb.S.squeeze().tolist()
    rpystring = " ".join([f"{x:.10f}" for x in rpy])
    posstring = " ".join([f"{x:.10f}" for x in pos])
    scalestring = " ".join([f"{x:.10f}" for x in scale])
    return [posstring, rpystring, scalestring]

def show_notification(
        export_complete: bool, 
        server: viser.ViserServer,
        output_dir: str) -> None:
    if export_complete:
        server.clear_notification()
        notif = server.add_notification(
                    title="Export complete!",
                    body="File saved under " + output_dir,
                    withCloseButton=True,
                    loading=False,
                    autoClose=5000,
                )
        notif.show()
    else: 
        server.clear_notification()
        notif = server.add_notification(
                    title="Export error!",
                    body="Please try again after a checkpoint is saved after 2000 steps.",
                    withCloseButton=True,
                    loading=False,
                    autoClose=5000,
                )


def populate_point_cloud_tab(
    server: viser.ViserServer,
    control_panel: ControlPanel,
    config_path: Path,
    viewing_gsplat: bool,
) -> None:
    if not viewing_gsplat:
        server.add_gui_markdown(
            "<small>Render depth, project to an oriented point cloud, and filter</small> "
        )
        num_points = server.add_gui_number(
            "# Points", initial_value=1_000_000, min=1, max=None, step=1
        )
        world_frame = server.add_gui_checkbox(
            "Save in world frame",
            False,
            hint=(
                "If checked, saves the point cloud in the same frame as the original dataset. Otherwise, uses the "
                "scaled and reoriented coordinate space expected by the NeRF models."
            ),
        )
        remove_outliers = server.add_gui_checkbox("Remove outliers", True)
        normals = server.add_gui_dropdown(
            "Normals",
            # TODO: options here could depend on what's available to the model.
            ("open3d", "model_output"),
            initial_value="open3d",
            hint="Normal map source.",
        )
        output_dir = server.add_gui_text(
            "Output Directory", initial_value="exports/pcd/"
        )
        export_button = server.add_gui_button("Export", icon=viser.Icon.TERMINAL_2)

        @export_button.on_click
        def _(event: viser.GuiEvent) -> None:
            assert event.client is not None
            notif = server.add_notification(
                        title="Exporting point cloud",
                        body="File will be saved under " + str(output_dir.value),
                        withCloseButton=True,
                        loading=True,
                        autoClose=False,
                    )
            notif.show()

            if control_panel.crop_obb is not None and control_panel.crop_viewport:
                posstring, rpystring, scalestring = get_crop_string(
                    control_panel.crop_obb, control_panel.crop_viewport
                )
            else: 
                posstring = rpystring = scalestring = None

            from nerfstudio.scripts.exporter import ExportPointCloud
            
            export = ExportPointCloud(
                load_config=config_path,
                output_dir=Path(output_dir.value),
                num_points=num_points.value,
                remove_outliers=remove_outliers.value,
                normal_method=normals.value,
                save_world_frame=world_frame.value,
                obb_center=posstring,
                obb_rotation=rpystring,
                obb_scale=scalestring,
            )
            export.main()

            show_notification(export_complete=export.complete,
                              server=server,
                              output_dir=str(output_dir.value))

    else:
        server.add_gui_markdown(
            "<small>Point cloud export is not currently supported with Gaussian Splatting</small>"
        )


def populate_mesh_tab(
    server: viser.ViserServer,
    control_panel: ControlPanel,
    config_path: Path,
    viewing_gsplat: bool,
) -> None:
    if not viewing_gsplat:
        server.add_gui_markdown(
            "<small>Render depth, project to an oriented point cloud, and run Poisson surface reconstruction</small>"
        )

        normals = server.add_gui_dropdown(
            "Normals",
            ("open3d", "model_output"),
            initial_value="open3d",
            hint="Source for normal maps.",
        )
        num_faces = server.add_gui_number("# Faces", initial_value=50_000, min=1)
        texture_resolution = server.add_gui_number(
            "Texture Resolution", min=8, initial_value=2048
        )
        output_dir = server.add_gui_text(
            "Output Directory", initial_value="exports/mesh/"
        )
        num_points = server.add_gui_number(
            "# Points", initial_value=1_000_000, min=1, max=None, step=1
        )
        remove_outliers = server.add_gui_checkbox("Remove outliers", True)

        export_button = server.add_gui_button("Export", icon=viser.Icon.TERMINAL_2)

        @export_button.on_click
        def _(event: viser.GuiEvent) -> None:
            assert event.client is not None
            notif = server.add_notification(
                        title="Exporting poisson mesh",
                        body="File will be saved under " + str(output_dir.value),
                        withCloseButton=True,
                        loading=True,
                        autoClose=False,
                    )
            notif.show()

            if control_panel.crop_obb is not None and control_panel.crop_viewport:
                posstring, rpystring, scalestring = get_crop_string(
                    control_panel.crop_obb, control_panel.crop_viewport
                )
            else: 
                posstring = rpystring = scalestring = None

            from nerfstudio.scripts.exporter import ExportPoissonMesh
                
            export = ExportPoissonMesh(
                load_config=config_path,
                output_dir=Path(output_dir.value),
                target_num_faces=num_faces.value,
                num_pixels_per_side=texture_resolution.value,
                num_points=num_points.value,
                remove_outliers=remove_outliers.value,
                normal_method=normals.value,
                obb_center=posstring,
                obb_rotation=rpystring,
                obb_scale=scalestring,
            )
            export.main()

            show_notification(export_complete=export.complete,
                              server=server,
                              output_dir=str(output_dir.value))

    else:
        server.add_gui_markdown(
            "<small>Mesh export is not currently supported with Gaussian Splatting</small>"
        )


def populate_splat_tab(
    server: viser.ViserServer,
    control_panel: ControlPanel,
    config_path: Path,
    viewing_gsplat: bool,
) -> None:
    if viewing_gsplat:
        server.add_gui_markdown("<small>Export ply of Gaussian Splat</small>")

        output_dir = server.add_gui_text(
            "Output Directory", initial_value="exports/splat/"
        )

        export_button = server.add_gui_button("Export", icon=viser.Icon.TERMINAL_2)

        @export_button.on_click
        def _(event: viser.GuiEvent) -> None:
            assert event.client is not None
            notif = server.add_notification(
                        title="Exporting gaussian splat",
                        body="File will be saved under " + str(output_dir.value),
                        withCloseButton=True,
                        loading=True,
                        autoClose=False,
                    )
            notif.show()

            if control_panel.crop_obb is not None and control_panel.crop_viewport:
                posstring, rpystring, scalestring = get_crop_string(
                    control_panel.crop_obb, control_panel.crop_viewport
                )
            else: 
                posstring = rpystring = scalestring = None

            from nerfstudio.scripts.exporter import ExportGaussianSplat

            export = ExportGaussianSplat(
                load_config=config_path,
                output_dir=Path(output_dir.value),
                obb_center=posstring,
                obb_rotation=rpystring,
                obb_scale=scalestring,
            )
            export.main()

            show_notification(export_complete=export.complete,
                              server=server,
                              output_dir=str(output_dir.value))

    else:
        server.add_gui_markdown(
            "<small>Splat export is only supported with Gaussian Splatting methods</small>"
        )
