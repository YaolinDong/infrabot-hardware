#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 YaolinDong
"""Render docs/images from the STEP files: python3 -B tools/render_previews.py [repo].

Needs cadquery-ocp, VTK, NumPy and Pillow. Parts in the assembly are matched to
parts.json by volume; anything unmatched is drawn as a purchased part.
"""
import json
import sys
from pathlib import Path

import numpy as np
from OCP.BRep import BRep_Tool
from OCP.BRepGProp import BRepGProp
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.STEPControl import STEPControl_Reader
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDF import TDF_Label, TDF_LabelSequence
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS
from OCP.XCAFDoc import XCAFDoc_DocumentTool
import vtk
from PIL import Image
from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray, vtk_to_numpy

ALUMINIUM = (178, 186, 196)
MOTOR = (78, 82, 90)
HIGHLIGHT = (232, 128, 40)
GHOST = (222, 224, 228)
# Assembly links in order; images are written as docs/images/links/<name>.png.
LINKS = ['baselink', 'link1', 'link2', 'link3', 'link4', 'link5', 'link6', 'link7']
# Y-up CAD frame to Z-up image frame.
Y_UP = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], float)


def mesh(shape, deflection):
    BRepMesh_IncrementalMesh(shape, deflection, False, 0.5, True)
    out = []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is not None:
            trsf = loc.Transformation()
            pts = np.array([[p.X(), p.Y(), p.Z()] for p in
                            (tri.Node(i).Transformed(trsf) for i in range(1, tri.NbNodes() + 1))])
            idx = np.array([tri.Triangle(i).Get() for i in range(1, tri.NbTriangles() + 1)]) - 1
            if face.Orientation() == TopAbs_REVERSED:
                idx = idx[:, ::-1]
            out.append(pts[idx])
        exp.Next()
    return np.concatenate(out) if out else np.zeros((0, 3, 3))


def volume(shape):
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return props.Mass()


def load_shape(path):
    reader = STEPControl_Reader()
    assert reader.ReadFile(str(path)) == IFSelect_RetDone, path
    reader.TransferRoots()
    return reader.OneShape()


def groups(assembly, volumes):
    """Return (link name, triangles, part id or None) for each component."""
    doc = TDocStd_Document(TCollection_ExtendedString('doc'))
    reader = STEPCAFControl_Reader()
    assert reader.ReadFile(str(assembly)) == IFSelect_RetDone
    reader.Transfer(doc)
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    roots = TDF_LabelSequence()
    shapes.GetFreeShapes(roots)
    links = TDF_LabelSequence()
    shapes.GetComponents_s(roots.Value(1), links)
    out = []
    for i in range(1, links.Length() + 1):
        link = links.Value(i)
        ref = TDF_Label()
        shapes.GetReferredShape_s(link, ref)
        parts = TDF_LabelSequence()
        shapes.GetComponents_s(ref, parts)
        # A link with no children is itself a single part.
        labels = [parts.Value(j) for j in range(1, parts.Length() + 1)] or [link]
        link_location = shapes.GetLocation_s(link)
        for part in labels:
            shape = shapes.GetShape_s(part)
            if part is not link:
                shape = shape.Moved(link_location)
            v = volume(shape)
            pid = next((k for vol, k in volumes if abs(vol - v) <= 1e-4 * vol + 0.1), None)
            out.append((i, mesh(shape, 0.5), pid))
    return out


def view_basis(azimuth, elevation):
    a, e = np.radians(azimuth), np.radians(elevation)
    eye = np.array([np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)])
    right = np.cross([0, 0, 1], eye)
    right /= np.linalg.norm(right)
    return eye, right, np.cross(eye, right)


def polydata(tris):
    """Triangle soup to a cleaned VTK mesh with split normals for flat faces and smooth curves."""
    pts = vtk.vtkPoints()
    pts.SetData(numpy_to_vtk(np.ascontiguousarray(tris.reshape(-1, 3)), deep=True))
    n = len(tris)
    cells = vtk.vtkCellArray()
    cells.SetData(numpy_to_vtkIdTypeArray(np.arange(0, 3 * n + 1, 3, dtype=np.int64), deep=True),
                  numpy_to_vtkIdTypeArray(np.arange(3 * n, dtype=np.int64), deep=True))
    poly = vtk.vtkPolyData()
    poly.SetPoints(pts)
    poly.SetPolys(cells)
    clean = vtk.vtkCleanPolyData()
    clean.SetInputData(poly)
    normals = vtk.vtkPolyDataNormals()
    normals.SetInputConnection(clean.GetOutputPort())
    normals.SetFeatureAngle(35)
    normals.SplittingOn()
    normals.ConsistencyOn()
    normals.Update()
    return normals.GetOutput()


class Renderer:
    """Off-screen z-buffered renderer with an orthographic camera."""
    SUPERSAMPLE = 2

    def __init__(self):
        self.ren = vtk.vtkRenderer()
        self.ren.SetBackground(1, 1, 1)
        self.ren.AutomaticLightCreationOff()
        kit = vtk.vtkLightKit()
        kit.SetKeyLightIntensity(0.85)
        kit.AddLightsToRenderer(self.ren)
        self.win = vtk.vtkRenderWindow()
        self.win.SetOffScreenRendering(1)
        self.win.SetMultiSamples(0)
        self.win.AddRenderer(self.ren)

    def frame(self, points, azimuth, elevation, size, margin=0.9):
        """Camera that fits points into size, reusable across several renders."""
        eye, right, up = view_basis(azimuth, elevation)
        u, v, d = points @ right, points @ up, points @ eye
        cu, cv = (u.min() + u.max()) / 2, (v.min() + v.max()) / 2
        half_h = max((v.max() - v.min()) / 2, (u.max() - u.min()) / 2 * size[1] / size[0]) / margin
        focal = cu * right + cv * up + (d.min() + d.max()) / 2 * eye
        dist = 4 * (d.max() - d.min() + 1)
        return focal, eye, up, half_h, dist

    @staticmethod
    def extent(points, eye, up):
        """Width and height in mm of points seen along eye."""
        eye, up = np.asarray(eye, float), np.asarray(up, float)
        return np.ptp(points @ np.cross(up, eye)), np.ptp(points @ up)

    @staticmethod
    def frame_axis(points, eye, up, px_per_mm, size):
        """Orthographic camera along eye at a fixed scale, centred in an image of size."""
        eye, up = np.asarray(eye, float), np.asarray(up, float)
        right = np.cross(up, eye)
        u, v, d = points @ right, points @ up, points @ eye
        focal = (u.min() + u.max()) / 2 * right + (v.min() + v.max()) / 2 * up + (d.min() + d.max()) / 2 * eye
        dist = 4 * (np.ptp(d) + 1)
        return focal, eye, up, size[1] / 2 / px_per_mm, dist

    def draw(self, meshes, camera, size):
        """meshes: (vtkPolyData, rgb 0-255). Returns a PIL image."""
        self.ren.RemoveAllViewProps()
        for poly, color in meshes:
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputData(poly)
            actor = vtk.vtkActor()
            actor.SetMapper(mapper)
            prop = actor.GetProperty()
            prop.SetColor(*(c / 255 for c in color))
            prop.SetAmbient(0.22)
            prop.SetDiffuse(0.8)
            prop.SetSpecular(0.12)
            prop.SetSpecularPower(20)
            self.ren.AddActor(actor)
        focal, eye, up, half_h, dist = camera
        cam = self.ren.GetActiveCamera()
        cam.ParallelProjectionOn()
        cam.SetFocalPoint(*focal)
        cam.SetPosition(*(focal + eye * dist))
        cam.SetViewUp(*up)
        cam.SetParallelScale(half_h)
        cam.SetClippingRange(dist / 20, dist * 2)
        k = self.SUPERSAMPLE
        self.win.SetSize(size[0] * k, size[1] * k)
        self.win.Render()
        grab = vtk.vtkWindowToImageFilter()
        grab.SetInput(self.win)
        grab.SetInputBufferTypeToRGB()
        grab.ReadFrontBufferOff()
        grab.Update()
        img = grab.GetOutput()
        w, h, _ = img.GetDimensions()
        arr = vtk_to_numpy(img.GetPointData().GetScalars()).reshape(h, w, 3)[::-1]
        return Image.fromarray(np.ascontiguousarray(arr)).resize(size, Image.LANCZOS)


# Camera angles in degrees (azimuth about Z, elevation), in the Z-up image frame.
ISO = (35, 20)
PART = (-50, 30)
# Orthographic views as (direction to the camera, image up). The front view shows the
# arm side-on; the left view looks from the viewer's left (-Y); the top view looks down.
FRONT_VIEW = ((1, 0, 0), (0, 0, 1))
LEFT_VIEW = ((0, -1, 0), (0, 0, 1))
TOP_VIEW = ((0, 0, 1), (-1, 0, 0))
# Every image in docs/images is rendered at this size.
IMAGE_SIZE = (1200, 900)
VIEW_PAD = 30


def scene(comps, highlight=None):
    """(vtkPolyData, colour) for every component, with one link highlighted if given."""
    out = []
    for link, poly, pid in comps:
        if highlight is not None and link != highlight:
            color = GHOST
        elif pid is None:
            color = MOTOR
        elif highlight is not None:
            color = HIGHLIGHT
        else:
            color = ALUMINIUM
        out.append((poly, color))
    return out


def load_assembly(repo, meta):
    by_volume = [(p['volume_mm3'], p['id']) for p in meta['parts']]
    comps = [(link, polydata(tris @ Y_UP.T), pid)
             for link, tris, pid in groups(repo / meta['assembly']['step'], by_volume)]
    points = np.concatenate([vtk_to_numpy(poly.GetPoints().GetData()) for _, poly, _ in comps])
    return comps, points


def main(repo):
    repo = Path(repo)
    meta = json.loads((repo / 'parts.json').read_text())
    out = repo / 'docs' / 'images'
    out.mkdir(parents=True, exist_ok=True)
    print('reading assembly')
    comps, points = load_assembly(repo, meta)
    matched = sum(1 for _, _, pid in comps if pid)
    print(f'{len(comps)} components, {matched} match a part file')
    r = Renderer()

    # Four images of one size for a 2 x 2 grid: isometric, front / left, top. The three views
    # share one scale and are centred, so they line up when shown at the same width.
    views = [('front', FRONT_VIEW), ('left', LEFT_VIEW), ('top', TOP_VIEW)]
    extents = [r.extent(points, eye, up) for _, (eye, up) in views]
    size = IMAGE_SIZE
    # One scale for all three views, chosen so the widest and the tallest view fit.
    px_per_mm = min((size[0] - 2 * VIEW_PAD) / max(e[0] for e in extents),
                    (size[1] - 2 * VIEW_PAD) / max(e[1] for e in extents))
    for name, (eye, up) in views:
        camera = r.frame_axis(points, eye, up, px_per_mm, size)
        r.draw(scene(comps), camera, size).save(out / f'view_{name}.png', optimize=True)
    r.draw(scene(comps), r.frame(points, *ISO, size), size).save(out / 'assembly.png', optimize=True)

    links_dir, parts_dir = out / 'links', out / 'parts'
    links_dir.mkdir(exist_ok=True)
    parts_dir.mkdir(exist_ok=True)
    camera = r.frame(points, *ISO, size)
    for i, name in enumerate(LINKS, start=1):
        r.draw(scene(comps, highlight=i), camera, size).save(links_dir / f'{name}.png', optimize=True)

    for p in meta['parts']:
        tris = mesh(load_shape(repo / p['step']), 0.1)
        poly = polydata(tris)
        pts = vtk_to_numpy(poly.GetPoints().GetData())
        r.draw([(poly, ALUMINIUM)], r.frame(pts, *PART, size), size).save(parts_dir / f'{p["id"]}.png', optimize=True)
    print('wrote', out)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[1])
