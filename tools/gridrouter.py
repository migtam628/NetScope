"""A small two-layer grid router for KiCad boards (pcbnew + numpy).

Written for this project so that board layout does not depend on running a
third-party autorouter.  It is deliberately simple:

  * a uniform grid (0.25 mm by default) over the board, two copper layers;
  * for the net being routed, every other net's copper is an obstacle grown by
    half the track width + the clearance (+ a small margin for the grid);
  * Dijkstra from the already-connected part of the net to the nearest
    unconnected pad, with a via cost; repeated until the net is one piece;
  * nets are routed one after another and never ripped up.

It is not clever and it does not guarantee a result: a net it cannot route is
reported, and KiCad's DRC remains the judge of what it produces.  No length
matching, no impedance control, no differential pairs.
"""
from __future__ import annotations

import heapq
import math

import numpy as np
import pcbnew

MARGIN = 0.04           # extra obstacle growth to cover diagonal steps between grid points


class GridRouter:
    def __init__(self, board, centre, size, grid=0.25, track=0.25, clearance=0.2, via=0.6, drill=0.3,
                 edge_clearance=0.5, hole_clearance=0.25, via_cost=12.0):
        self.board, self.g = board, grid
        self.cx, self.cy = centre
        self.w, self.h = size
        self.track, self.clear, self.via, self.drill = track, clearance, via, drill
        self.edge, self.hole = edge_clearance, hole_clearance
        self.via_cost = via_cost
        self.nx, self.ny = int(round(self.w / grid)) + 1, int(round(self.h / grid)) + 1
        xs = -self.w / 2 + np.arange(self.nx) * grid
        ys = -self.h / 2 + np.arange(self.ny) * grid
        self.X, self.Y = np.meshgrid(xs, ys)                 # shape (ny, nx)
        self.shapes: list[dict] = []                         # copper and holes, see _add
        self.failed: list[str] = []
        self._scan()

    # ---- coordinates -------------------------------------------------------
    def _xy(self, v):
        return pcbnew.ToMM(v.x) - self.cx, self.cy - pcbnew.ToMM(v.y)

    def _pt(self, x, y):
        return pcbnew.VECTOR2I(pcbnew.FromMM(self.cx + x), pcbnew.FromMM(self.cy - y))

    def _cell(self, x, y):
        return int(round((y + self.h / 2) / self.g)), int(round((x + self.w / 2) / self.g))

    def _pos(self, j, i):
        return -self.w / 2 + i * self.g, -self.h / 2 + j * self.g

    # ---- board contents ------------------------------------------------------
    def _add(self, kind, layers, net, **geom):
        self.shapes.append({"kind": kind, "layers": layers, "net": net, **geom})

    def _scan(self):
        for f in self.board.GetFootprints():
            for p in f.Pads():
                bb = p.GetBoundingBox()
                x0, y1 = self._xy(pcbnew.VECTOR2I(bb.GetLeft(), bb.GetTop()))
                x1, y0 = self._xy(pcbnew.VECTOR2I(bb.GetRight(), bb.GetBottom()))
                layers = tuple(k for k, layer in enumerate((pcbnew.F_Cu, pcbnew.B_Cu)) if p.IsOnLayer(layer))
                if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    self._add("hole", (0, 1), None, rect=(x0, y0, x1, y1))
                elif layers:
                    self._add("pad", layers, p.GetNetname() or None, rect=(x0, y0, x1, y1), centre=self._xy(p.GetPosition()),
                              ref=f.GetReference(), num=p.GetNumber())
        for t in self.board.GetTracks():
            self._register(t)

    def _register(self, t):
        net = t.GetNetname() or None
        if t.GetClass() == "PCB_VIA":
            self._add("via", (0, 1), net, at=self._xy(t.GetPosition()), r=pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) / 2)
        else:
            self._add("seg", (0 if t.GetLayer() == pcbnew.F_Cu else 1,), net, a=self._xy(t.GetStart()),
                      b=self._xy(t.GetEnd()), r=pcbnew.ToMM(t.GetWidth()) / 2)

    # ---- rasterising -----------------------------------------------------------
    def _grow(self, s, by):
        """Boolean (ny, nx) array: grid points closer than `by` to the shape."""
        if s["kind"] in ("pad", "hole"):
            x0, y0, x1, y1 = s["rect"]
            dx = np.maximum(np.maximum(x0 - self.X, self.X - x1), 0)
            dy = np.maximum(np.maximum(y0 - self.Y, self.Y - y1), 0)
            return np.hypot(dx, dy) < by
        if s["kind"] == "via":
            return np.hypot(self.X - s["at"][0], self.Y - s["at"][1]) < s["r"] + by
        (ax, ay), (bx, by_) = s["a"], s["b"]
        vx, vy = bx - ax, by_ - ay
        L2 = vx * vx + vy * vy
        t = np.clip(((self.X - ax) * vx + (self.Y - ay) * vy) / L2, 0, 1) if L2 else 0
        return np.hypot(self.X - (ax + t * vx), self.Y - (ay + t * vy)) < s["r"] + by

    def _inside(self, s):
        """Grid points safely inside the shape's copper, so that a track ending there really touches it.
        Pads are treated as a stadium along their long axis, which is exact for round and oval pads
        and leaves out only the corners of rectangular ones."""
        if s["kind"] != "pad":
            return self._grow(s, 1e-6)
        x0, y0, x1, y1 = s["rect"]
        r = min(x1 - x0, y1 - y0) / 2
        if x1 - x0 >= y1 - y0:
            a, b = (x0 + r, (y0 + y1) / 2), (x1 - r, (y0 + y1) / 2)
        else:
            a, b = ((x0 + x1) / 2, y0 + r), ((x0 + x1) / 2, y1 - r)
        return self._grow({"kind": "seg", "a": a, "b": b, "r": r}, -0.05)

    def _masks(self, net, width):
        """(blocked[2], via_blocked) for routing `net` with a track of `width`."""
        blocked = np.zeros((2, self.ny, self.nx), bool)
        via_blocked = np.zeros((self.ny, self.nx), bool)
        edge = (np.minimum(self.X + self.w / 2, self.w / 2 - self.X) < self.edge + width / 2) | \
               (np.minimum(self.Y + self.h / 2, self.h / 2 - self.Y) < self.edge + width / 2)
        blocked[:] = edge
        via_blocked |= (np.minimum(self.X + self.w / 2, self.w / 2 - self.X) < self.edge + self.via / 2) | \
                       (np.minimum(self.Y + self.h / 2, self.h / 2 - self.Y) < self.edge + self.via / 2)
        own = np.zeros((2, self.ny, self.nx), bool)
        for s in self.shapes:
            if s["net"] is not None and s["net"] == net:
                grown = self._inside(s)                        # our own copper is always walkable
                for k in s["layers"]:
                    own[k] |= grown
                if len(s["layers"]) == 2:                      # but a new via must keep its hole clear of our own holes
                    via_blocked |= self._grow(s, self.hole + self.drill / 2 + MARGIN) & ~self._grow(s, 1e-6) \
                        if s["kind"] == "pad" else self._grow(s, self.hole + self.drill / 2 + MARGIN) & \
                        ~(np.hypot(self.X - s["at"][0], self.Y - s["at"][1]) < 1e-6)
                continue
            gap = self.hole if s["kind"] == "hole" else self.clear
            t_grow = self._grow(s, gap + width / 2 + MARGIN)
            v_grow = self._grow(s, gap + self.via / 2 + MARGIN)
            for k in s["layers"]:
                blocked[k] |= t_grow
            via_blocked |= v_grow                              # a via is copper on both layers
            if s["kind"] in ("hole",) or len(s["layers"]) == 2:
                via_blocked |= self._grow(s, self.hole + self.drill / 2 + MARGIN)
        blocked &= ~own
        return blocked, via_blocked, own

    # ---- routing ------------------------------------------------------------------
    def route(self, net, width=None, layers=(0, 1)):
        """Connect every pad and existing track of `net`.  Returns True when the net is one piece."""
        width = width or self.track
        blocked, via_blocked, own = self._masks(net, width)
        groups = self._groups(net, own)
        if len(groups) <= 1:
            return True
        tree = set(groups.pop(0))
        ok = True
        while groups:
            targets = {}
            for gi, grp in enumerate(groups):
                for c in grp:
                    targets[c] = gi
            path = self._search(tree, targets, blocked, via_blocked, layers)
            if path is None:
                where = ", ".join("(%.2f, %.2f) %s" % (*self._pos(g[0][1], g[0][2]), "FB"[g[0][0]]) for g in groups[:6])
                self.failed.append(f"{net}: {len(groups)} piece(s) left unconnected, at {where}")
                ok = False
                break
            gi = targets[path[-1]]
            tree |= set(path) | set(groups.pop(gi))
            self._emit(net, width, path)
        return ok

    def _groups(self, net, own):
        """Connected pieces of the net's existing copper, as sets of (layer, j, i) grid cells."""
        cells = {(k, int(j), int(i)) for k in (0, 1) for j, i in zip(*np.nonzero(own[k]))}
        thru = np.zeros((self.ny, self.nx), bool)              # where the net's own copper joins the layers
        for s in self.shapes:
            if s["net"] == net and len(s["layers"]) == 2 and s["kind"] in ("pad", "via"):
                thru |= self._inside(s)
        # every pad must contribute at least one cell, even if no grid point falls inside it
        for s in self.shapes:
            if s["kind"] == "pad" and s["net"] == net:
                j, i = self._cell(*s["centre"])
                for k in s["layers"]:
                    cells.add((k, j, i))
        seen, groups = set(), []
        for c in sorted(cells):
            if c in seen:
                continue
            grp, stack = [], [c]
            seen.add(c)
            while stack:
                k, j, i = stack.pop()
                grp.append((k, j, i))
                nbrs = [(k, j + dj, i + di) for dj in (-1, 0, 1) for di in (-1, 0, 1) if dj or di]
                if thru[j, i]:
                    nbrs.append((1 - k, j, i))
                for n in nbrs:
                    if n in cells and n not in seen:
                        seen.add(n)
                        stack.append(n)
            groups.append(grp)
        groups.sort(key=len, reverse=True)
        return groups

    def _search(self, tree, targets, blocked, via_blocked, layers):
        dist = {c: 0.0 for c in tree}
        prev = {}
        heap = [(0.0, c) for c in tree]
        heapq.heapify(heap)
        S2 = math.sqrt(2)
        while heap:
            d, c = heapq.heappop(heap)
            if d > dist.get(c, 1e18):
                continue
            if c in targets:
                path = [c]
                while path[-1] in prev:
                    path.append(prev[path[-1]])
                return path[::-1]
            k, j, i = c
            for dj, di, cost in ((0, 1, 1), (0, -1, 1), (1, 0, 1), (-1, 0, 1), (1, 1, S2), (1, -1, S2), (-1, 1, S2), (-1, -1, S2)):
                nj, ni = j + dj, i + di
                if not (0 <= nj < self.ny and 0 <= ni < self.nx) or blocked[k, nj, ni]:
                    continue
                if dj and di and (blocked[k, j, ni] or blocked[k, nj, i]):
                    continue                                   # no cutting corners past an obstacle
                n = (k, nj, ni)
                nd = d + cost
                if nd < dist.get(n, 1e18):
                    dist[n], prev[n] = nd, c
                    heapq.heappush(heap, (nd, n))
            ok = 1 - k
            if ok in layers and not via_blocked[j, i] and not blocked[ok, j, i]:
                n = (ok, j, i)
                nd = d + self.via_cost
                if nd < dist.get(n, 1e18):
                    dist[n], prev[n] = nd, c
                    heapq.heappush(heap, (nd, n))
        return None

    def _emit(self, net, width, path):
        info = self.board.FindNet(net)
        run = [path[0]]
        for c in path[1:] + [None]:
            if c is not None and c[0] == run[-1][0]:
                run.append(c)
                continue
            self._emit_run(info, width, run)
            if c is not None:                                  # layer change: via here
                v = pcbnew.PCB_VIA(self.board)
                v.SetPosition(self._pt(*self._pos(run[-1][1], run[-1][2])))
                v.SetWidth(pcbnew.F_Cu, pcbnew.FromMM(self.via))
                v.SetDrill(pcbnew.FromMM(self.drill))
                v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                v.SetNet(info)
                self.board.Add(v)
                self._register(v)
                run = [c]

    def _emit_run(self, info, width, run):
        if len(run) < 2:
            return
        layer = pcbnew.F_Cu if run[0][0] == 0 else pcbnew.B_Cu
        start = run[0]
        for a, b, c in zip(run, run[1:], run[2:] + [None]):
            if c is not None and (b[1] - a[1], b[2] - a[2]) == (c[1] - b[1], c[2] - b[2]):
                continue                                       # still going straight
            t = pcbnew.PCB_TRACK(self.board)
            t.SetStart(self._pt(*self._pos(start[1], start[2])))
            t.SetEnd(self._pt(*self._pos(b[1], b[2])))
            t.SetWidth(pcbnew.FromMM(width))
            t.SetLayer(layer)
            t.SetNet(info)
            self.board.Add(t)
            self._register(t)
            start = b

    def tie_pads(self, net, width=None):
        """Short link from each pad centre to the nearest grid point, for pads that sit off the grid."""
        width = width or self.track
        info = self.board.FindNet(net)
        for s in [s for s in self.shapes if s["kind"] == "pad" and s["net"] == net]:
            x, y = s["centre"]
            gx, gy = self._pos(*self._cell(x, y))
            if math.hypot(gx - x, gy - y) > 0.005:
                for k in s["layers"][:1]:
                    t = pcbnew.PCB_TRACK(self.board)
                    t.SetStart(self._pt(x, y))
                    t.SetEnd(self._pt(gx, gy))
                    t.SetWidth(pcbnew.FromMM(min(width, 0.2)))
                    t.SetLayer(pcbnew.F_Cu if k == 0 else pcbnew.B_Cu)
                    t.SetNet(info)
                    self.board.Add(t)
                    self._register(t)

    def drop_vias(self, net, wanted=lambda ref: True, reach=2.0, width=None):
        """Give each single-layer pad of `net` its own via close by, joined by a short straight track.
        Done before routing, so that a small ground pad cannot be boxed in by the signals around it."""
        width = width or self.track
        info, made = self.board.FindNet(net), 0
        for s in [s for s in self.shapes if s["kind"] == "pad" and s["net"] == net and len(s["layers"]) == 1
                  and wanted(s["ref"])]:
            blocked, via_blocked, _own = self._masks(net, width)        # includes the vias dropped so far
            k, (x, y) = s["layers"][0], s["centre"]
            j0, i0 = self._cell(x, y)
            n = int(reach / self.g)
            best = None
            for j in range(max(0, j0 - n), min(self.ny, j0 + n + 1)):
                for i in range(max(0, i0 - n), min(self.nx, i0 + n + 1)):
                    if via_blocked[j, i] or blocked[0, j, i] or blocked[1, j, i]:
                        continue
                    vx, vy = self._pos(j, i)
                    dist = math.hypot(vx - x, vy - y)
                    if dist > reach or dist < self.via / 2 or (best and dist >= best[0]):
                        continue
                    steps = max(2, int(dist / (self.g / 2)))
                    line = [self._cell(x + (vx - x) * t / steps, y + (vy - y) * t / steps) for t in range(steps + 1)]
                    if any(blocked[k, a, b] for a, b in line):
                        continue
                    best = (dist, vx, vy)
            if not best:
                continue
            _, vx, vy = best
            t = pcbnew.PCB_TRACK(self.board)
            t.SetStart(self._pt(x, y))
            t.SetEnd(self._pt(vx, vy))
            t.SetWidth(pcbnew.FromMM(width))
            t.SetLayer(pcbnew.F_Cu if k == 0 else pcbnew.B_Cu)
            t.SetNet(info)
            self.board.Add(t)
            self._register(t)
            v = pcbnew.PCB_VIA(self.board)
            v.SetPosition(self._pt(vx, vy))
            v.SetWidth(pcbnew.F_Cu, pcbnew.FromMM(self.via))
            v.SetDrill(pcbnew.FromMM(self.drill))
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            v.SetNet(info)
            self.board.Add(v)
            self._register(v)
            made += 1
        return made

    def stitch(self, net, pitch=4.0, offset=(0.0, 0.0)):
        """Vias of `net` on a coarse grid wherever one fits, to tie the two layers' pours together."""
        blocked, via_blocked, _own = self._masks(net, self.via)
        info, step, count = self.board.FindNet(net), int(round(pitch / self.g)), 0
        j0, i0 = self._cell(-self.w / 2 + pitch / 2 + offset[0], -self.h / 2 + pitch / 2 + offset[1])[::-1][::-1]
        for j in range(j0 % step, self.ny, step):
            for i in range(i0 % step, self.nx, step):
                if via_blocked[j, i] or blocked[0, j, i] or blocked[1, j, i]:
                    continue
                v = pcbnew.PCB_VIA(self.board)
                v.SetPosition(self._pt(*self._pos(j, i)))
                v.SetWidth(pcbnew.F_Cu, pcbnew.FromMM(self.via))
                v.SetDrill(pcbnew.FromMM(self.drill))
                v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                v.SetNet(info)
                self.board.Add(v)
                self._register(v)
                count += 1
        return count

    def trim_stubs(self, stubs):
        """`stubs` are tracks drawn from a pad centre (start) outwards (end) before routing.  Cut each
        back to the furthest point where something else of its net attaches, so no tail is left dangling;
        remove it if nothing attaches beyond the pad."""
        ends = {}
        for t in self.board.GetTracks():
            pts = [t.GetPosition()] if t.GetClass() == "PCB_VIA" else [t.GetStart(), t.GetEnd()]
            for p in pts:
                ends.setdefault((t.GetNetCode(), p.x, p.y), []).append(t)
        for stub in stubs:
            a, b = stub.GetStart(), stub.GetEnd()
            length = math.hypot(b.x - a.x, b.y - a.y)
            best = 0.0
            for (code, x, y), owners in ends.items():
                owners = [o for o in owners if o.m_Uuid.AsString() != stub.m_Uuid.AsString()]
                if code != stub.GetNetCode() or not owners:
                    continue
                if any(o.GetClass() != "PCB_VIA" and o.GetLayer() != stub.GetLayer() for o in owners) and \
                        not any(o.GetClass() == "PCB_VIA" or o.GetLayer() == stub.GetLayer() for o in owners):
                    continue
                t = ((x - a.x) * (b.x - a.x) + (y - a.y) * (b.y - a.y)) / (length * length)
                px, py = a.x + t * (b.x - a.x), a.y + t * (b.y - a.y)
                if -1e-6 <= t <= 1 + 1e-6 and math.hypot(px - x, py - y) < pcbnew.FromMM(0.01):
                    best = max(best, t)
            if best <= 1e-6:
                self.board.Remove(stub)
            elif best < 1 - 1e-6:
                stub.SetEnd(pcbnew.VECTOR2I(int(round(a.x + best * (b.x - a.x))), int(round(a.y + best * (b.y - a.y)))))

