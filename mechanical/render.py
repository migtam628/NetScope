#!/usr/bin/env python3
"""Shaded renders of the enclosure and board assemblies from mechanical/out/*.stl.

    python mechanical/enclosure.py && python mechanical/render.py

Plain lit-geometry images (VTK, off-screen) for design review.  They show the
CAD concept as modelled: flat colours, box-shaped parts, no keycaps, labels,
textures or display content.  They are not product photographs.
"""
from pathlib import Path

import vtk

OUT = Path(__file__).resolve().parent / "out"
RENDERS = Path(__file__).resolve().parent / "renders"

SHELL, DOOR, BUMPER = (0.17, 0.19, 0.22), (0.24, 0.27, 0.31), (0.98, 0.78, 0.18)
PARTS = {  # name: (colour, opacity)
    "front_shell": (SHELL, 1.0), "rear_shell": (SHELL, 1.0), "battery_door": (DOOR, 1.0),
    "bumper": (BUMPER, 1.0), "ref_display": ((0.03, 0.04, 0.06), 1.0),
    "pcb_main": ((0.05, 0.38, 0.20), 1.0), "pcb_lower": ((0.05, 0.38, 0.20), 1.0),
    "ref_cells": ((0.20, 0.45, 0.80), 1.0),
}


def actor(name: str, offset=(0, 0, 0)) -> vtk.vtkActor:
    r = vtk.vtkSTLReader()
    r.SetFileName(str(OUT / f"{name}.stl"))
    n = vtk.vtkPolyDataNormals()
    n.SetInputConnection(r.GetOutputPort())
    n.SetFeatureAngle(40)
    m = vtk.vtkPolyDataMapper()
    m.SetInputConnection(n.GetOutputPort())
    a = vtk.vtkActor()
    a.SetMapper(m)
    colour, opacity = PARTS[name]
    p = a.GetProperty()
    p.SetColor(*colour)
    p.SetOpacity(opacity)
    p.SetAmbient(0.25)
    p.SetDiffuse(0.75)
    p.SetSpecular(0.25)
    p.SetSpecularPower(30)
    a.SetPosition(*offset)
    return a


def shot(filename: str, items: dict, cam: tuple, up=(0, 1, 0), size=(1400, 1400), zoom=1.0) -> None:
    ren = vtk.vtkRenderer()
    ren.SetBackground(0.95, 0.96, 0.97)
    ren.SetBackground2(0.80, 0.83, 0.87)
    ren.GradientBackgroundOn()
    for name, off in items.items():
        ren.AddActor(actor(name, off))
    win = vtk.vtkRenderWindow()
    win.SetOffScreenRendering(1)
    win.SetMultiSamples(8)
    win.AddRenderer(ren)
    win.SetSize(*size)
    c = ren.GetActiveCamera()
    c.SetFocalPoint(0, 0, 0)
    c.SetPosition(*cam)
    c.SetViewUp(*up)
    c.SetViewAngle(22)
    ren.ResetCamera()
    c.Zoom(zoom)
    ren.ResetCameraClippingRange()
    win.Render()
    w2i = vtk.vtkWindowToImageFilter()
    w2i.SetInput(win)
    w2i.Update()
    wr = vtk.vtkPNGWriter()
    wr.SetFileName(str(RENDERS / filename))
    wr.SetInputConnection(w2i.GetOutputPort())
    wr.Write()


def main() -> None:
    RENDERS.mkdir(exist_ok=True)
    z = (0, 0, 0)
    closed = {n: z for n in ("front_shell", "rear_shell", "battery_door", "bumper", "ref_display")}
    shot("01_front.png", closed, (140, -260, 520), zoom=1.25)
    shot("02_back.png", closed, (-160, -260, -520), zoom=1.25)
    shot("03_top_end_ports.png", closed, (120, 520, 200), up=(0, 0, 1), zoom=1.1)
    inside = {"rear_shell": z, "pcb_main": z, "pcb_lower": z, "ref_cells": z}
    shot("04_boards_in_rear_shell.png", inside, (120, -220, 520), zoom=1.25)
    boards = {"pcb_main": z, "pcb_lower": z, "ref_cells": z, "ref_display": z}
    shot("05_boards_back_side.png", boards, (-200, -240, -480), zoom=1.2)
    exploded = {"front_shell": (0, 0, 90), "ref_display": (0, 0, 50), "pcb_main": (0, 0, 10),
                "pcb_lower": (0, 0, 10), "ref_cells": (0, 0, -30), "rear_shell": (0, 0, -70),
                "battery_door": (0, 0, -105), "bumper": (0, 0, -70)}
    shot("06_exploded.png", exploded, (520, -260, 300), up=(0, 0, 1), size=(1600, 1400), zoom=1.15)
    print("renders written to", RENDERS)


if __name__ == "__main__":
    main()
