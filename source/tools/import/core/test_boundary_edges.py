"""Boundary placement regressions: protected road edges, curves, invalid widening."""
import unittest
import numpy as np
from build_more import corridor_lines
from road_footprint import union_boundary, check_height_separation


class BoundaryEdges(unittest.TestCase):
    def rows(self):
        # Closed ring with sharp changes: downsampling must miss real edge vertices.
        rows = []
        for a in np.linspace(0, 2*np.pi, 20, endpoint=False):
            r = np.array([np.cos(a), 0., np.sin(a)])
            p = np.stack([r*7., r*10., r*13.])
            p[:,1] = .2*np.cos(a)
            rows.append((p, -3, 6))
        return rows

    def test_exact_edges_without_road_mutation(self):
        rows = self.rows(); before = [p.tobytes() for p,_,_ in rows]
        left, right, *_ = corridor_lines(rows, every=1, inset=0.)
        self.assertEqual(len(left), len(rows))
        for j,(p,_,_) in enumerate(rows):
            np.testing.assert_array_equal(left[j], p[0,[0,2]])
            np.testing.assert_array_equal(right[j], p[-1,[0,2]])
        self.assertEqual(before, [p.tobytes() for p,_,_ in rows])
        # Old four-slice chords visibly cut through this bend.
        oldl, oldr, *_ = corridor_lines(rows)
        self.assertLess(np.linalg.norm((np.array(oldr[0])+oldr[1])/2), 12.5)

    def test_default_remains_legacy(self):
        rows = self.rows()
        actual = corridor_lines(rows)
        left=[];right=[];y=[]
        for p,_,_ in rows[::4]:
            d=p[-1]-p[0];d/=np.linalg.norm(d)
            left.append(tuple((p[0]+d*.5)[[0,2]]));right.append(tuple((p[-1]-d*.5)[[0,2]]));y.extend([p[0,1],p[-1,1]])
        self.assertEqual(actual, (left,right,min(y),max(y)))

    def test_steep_bank_floor_probes_include_crossfall(self):
        from unittest.mock import patch
        from build_more import add_walls
        rows = self.rows()
        for p, _, _ in rows:
            p[:, 1] = [0., 7., 14.]
        before = [p.tobytes() for p, _, _ in rows]
        # A fixed 12 m drop from the high side is still above the correctly
        # generated floor. Only the validation probe may change, not the road.
        with patch('build_more.set_boundary'), patch('build_more.log'):
            stats = add_walls(None, rows, [0], 0, 0, every=1,
                              terrain=True, inset=0., footprint_boundary=True)
        self.assertEqual(stats['under_distance'], 26.)
        self.assertEqual(stats['free'], stats['road_points'])
        self.assertEqual(stats['under'], stats['road_points'])
        self.assertEqual(stats['over'], stats['road_points'])
        self.assertEqual(before, [p.tobytes() for p, _, _ in rows])

    def test_invalid_settings_refused(self):
        for step in [0,-1,1.5,True]:
            with self.assertRaises(ValueError):corridor_lines(self.rows(),every=step)
        for inset in [-.1,float('nan'),float('inf')]:
            with self.assertRaises(ValueError):corridor_lines(self.rows(),inset=inset)


class BankedVisibleSurface(unittest.TestCase):
    def test_asphalt_triangulation_difference_does_not_remove_support(self):
        from unittest.mock import patch
        import build_classic as BC
        class Collision:
            def at2(self,x,z,y): return (0.,0)
        class Visible:
            def at2(self,x,z,y): return (.32 if abs(x)<=10 else 1.,0)
        class Walls:
            def blocked(self,p,q,y): return abs(q[0])>10
        p=np.array([[0.,0.,0.]])
        lat=np.array([[1.,0.,0.]])
        vis=(Visible(),['asphalt'],Walls())
        with patch.object(BC,'EDGE_VISUAL',.3), patch.object(BC,'EDGE_VISUAL_RIGHT',None):
            old=BC.classic_edges(Collision(),p,lat,np.zeros(1),15,vis)
        with patch.object(BC,'EDGE_VISUAL',.3), patch.object(BC,'EDGE_VISUAL_RIGHT',.4):
            new=BC.classic_edges(Collision(),p,lat,np.zeros(1),15,vis)
        self.assertEqual(old[1][0],3.5)
        self.assertEqual(new[1][0],10.)
        # Increased visual tolerance cannot walk through an upright wall or the
        # truly raised surface beyond it; it only accepts the asphalt mismatch.
        self.assertEqual(new[0][0],3.5)  # inner-side curb rule remains unchanged


class FootprintUnion(unittest.TestCase):
    @staticmethod
    def oracle(quads):
        def inside(pt):
            x,z = pt
            for q in quads:
                for a,b,c in ((q[0],q[1],q[2]),(q[0],q[2],q[3])):
                    den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
                    if abs(den)<1e-12:continue
                    u=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(z-c[1]))/den
                    v=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(z-c[1]))/den
                    if min(u,v,1-u-v)>=-1e-10:return True
            return False
        return inside

    def test_overlapping_slices_have_no_internal_collision_walls(self):
        # Overlapping quads: the raw longitudinal lines and a slice end lie
        # inside the actual drivable union; none may become an invisible wall.
        q=[((0.,0.),(3.,0.),(3.,2.),(0.,2.)),
           ((2.,1.),(4.,1.),(4.,3.),(2.,3.))]
        inside=self.oracle(q);edges,sources,stats=union_boundary(q,inside)
        self.assertAlmostEqual(sum(np.linalg.norm(np.array(b)-a) for a,b,_ in edges),14.)
        self.assertEqual(stats['boundary_segments'],8)
        for a,b,(nx,nz,d) in edges:
            m=(np.array(a)+b)/2;n=np.array([nx,nz])
            self.assertTrue(inside(m+n*.01));self.assertFalse(inside(m-n*.01))

    def test_height_separated_decks_are_rejected(self):
        q=[((0.,0.),(3.,0.),(3.,2.),(0.,2.)),
           ((2.,1.),(4.,1.),(4.,3.),(2.,3.)),
           ((10.,10.),(11.,10.),(11.,11.),(10.,11.))]
        with self.assertRaisesRegex(ValueError,'height-separated'):
            check_height_separation(q,[0.,0.,8.])
        self.assertEqual(check_height_separation(q,[0.,0.,0.])['overlapping_decks'],0)

    def test_returned_oracle_keeps_native_triangle_buffer_alive(self):
        import array,gc,bsp_build
        left=[(-2.,-2.),(2.,-2.),(2.,2.),(-2.,2.)]
        right=[(-1.,-1.),(1.,-1.),(1.,1.),(-1.,1.)]
        *_,inside=bsp_build.build_corridor(left,right)
        gc.collect()
        # Reuse small allocation pools; a dangling C pointer previously survived
        # simple immediate calls but read unrelated data after the next build.
        churn=[array.array('d',[99.]*48) for _ in range(100)]
        self.assertTrue(inside((1.5,0.)))
        self.assertFalse(inside((0.,0.)))
        self.assertFalse(inside((3.,0.)))

    def test_folded_quad_keeps_exposed_cross_slice_edges(self):
        # A bow-tie slice pair is represented by the same two triangles as the
        # road. Its exposed diagonal must be retained; simple L/R loops fail.
        q=[((0.,0.),(3.,2.),(3.,0.),(0.,2.))]
        inside=self.oracle(q);edges,sources,stats=union_boundary(q,inside)
        self.assertGreater(len(edges),4)
        for a,b,(nx,nz,d) in edges:
            m=(np.array(a)+b)/2;n=np.array([nx,nz])
            self.assertTrue(inside(m+n*.001));self.assertFalse(inside(m-n*.001))


if __name__ == '__main__': unittest.main()