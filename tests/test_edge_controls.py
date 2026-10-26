"""Reversible edge-control and local MCU-visualization contracts."""
import importlib.util
import math
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(importlib.util.find_spec('pcbnew'),'requires pcbnew')
class EdgeControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pcbnew
        cls.k=pcbnew;cls.board=pcbnew.LoadBoard(str(ROOT/'hw/remake.kicad_pcb'))
        cls.parts={f.GetReference():f for f in cls.board.GetFootprints()}

    def test_power_is_one_reversible_component_with_one_shared_hole_pair(self):
        self.assertIn('PWR1',self.parts)
        self.assertNotIn('PWR_L1',self.parts);self.assertNotIn('PWR_R1',self.parts)
        f=self.parts['PWR1']
        holes=[p for p in f.Pads() if p.GetDrillSize().x]
        self.assertEqual(len(holes),2)
        # The shared locating pair is centred on PWR1 and spaced 3 mm;
        # moving the component/board must not invalidate this contract.
        a,b=[p.GetPosition() for p in holes]
        self.assertAlmostEqual(self.k.ToMM((a-b).EuclideanNorm()),3.0,places=5)
        self.assertEqual((a.x+b.x,a.y+b.y),
                         (2*f.GetPosition().x,2*f.GetPosition().y))
        self.assertTrue(all(p.GetDrillSize()==self.k.VECTOR2I(self.k.FromMM(.9),self.k.FromMM(.9))
                            for p in holes))
        for layer in [self.k.F_Cu,self.k.B_Cu]:
            for number,net in [('2','BAT+'),('3','BAT_SW')]:
                pads=[p for p in f.Pads() if p.GetNumber()==number and p.IsOnLayer(layer)]
                self.assertEqual(len(pads),1);self.assertEqual(pads[0].GetNetname(),net)

    def test_reset_uses_the_official_side_push_no_boss_land_pattern(self):
        for ref,layer in [('RST_L1',self.k.F_Cu),('RST_R1',self.k.B_Cu)]:
            f=self.parts[ref]
            self.assertEqual(f.GetValue(),'EVQPUJ02K')
            self.assertEqual(str(f.GetFPID().GetLibItemName()),'SW_SPST_Panasonic_EVQPUJ02K')
            self.assertFalse(any(p.GetDrillSize().x for p in f.Pads()))
            for number,net in [('1','GND'),('2','RESET')]:
                pads=[p for p in f.Pads() if p.GetNumber()==number]
                self.assertEqual(len(pads),2)
                self.assertTrue(all(p.IsOnLayer(layer) and p.GetNetname()==net for p in pads))

    def test_both_reset_actuator_faces_point_out_through_the_same_edge(self):
        faces=[]
        for ref in ['RST_L1','RST_R1']:
            # Official actuator-tip stroke is 2.6 mm long; its face must lie
            # beyond the board edge on BOTH population alternatives.
            tips=[g for g in self.parts[ref].GraphicalItems()
                  if isinstance(g,self.k.PCB_SHAPE)
                  and abs(self.k.ToMM((g.GetEnd()-g.GetStart()).EuclideanNorm())-2.6)<1e-5]
            self.assertEqual(len(tips),1,ref)
            points=[tips[0].GetStart(),tips[0].GetEnd()]
            faces.append({(p.x,p.y) for p in points})
            for point in points:
                # Intersect the actual outline at the tip's Y, not a stale
                # absolute board coordinate. The actuator must project past
                # the electronics-side edge in both assembly alternatives.
                crossings=[]
                for edge in self.board.GetDrawings():
                    if edge.GetLayer()!=self.k.Edge_Cuts or edge.GetShapeStr()!='Line':
                        continue
                    a,b=edge.GetStart(),edge.GetEnd()
                    if a.y!=b.y and min(a.y,b.y)<=point.y<=max(a.y,b.y):
                        crossings.append(a.x+(point.y-a.y)*(b.x-a.x)/(b.y-a.y))
                self.assertTrue(crossings,ref)
                self.assertGreater(point.x,max(crossings),ref)
        self.assertEqual(faces[0],faces[1],'front/back actuator faces must coincide')

    def test_both_mcu_models_align_native_header_rows_to_the_keyboard_socket(self):
        f=self.parts['U1'];c=f.GetPosition()
        socket={(round(self.k.ToMM(p.GetPosition().x-c.x),4),
                 round(-self.k.ToMM(p.GetPosition().y-c.y),4))
                for p in f.Pads() if p.GetNumber().isdigit() and 1<=int(p.GetNumber())<=24}
        # Datums measured from the supplied STEP's PCB circular edges, not
        # invented around its origin. KiCad uses T Rz(-z) Ry(-y) Rx(-x).
        for m in f.Models():
            points=set()
            for i in range(12):
                for y in [-7.62,7.62]:
                    x,z=-12.81+2.54*i,0
                    for axis,degrees in [('x',m.m_Rotation.x),('y',m.m_Rotation.y),('z',m.m_Rotation.z)]:
                        a=math.radians(-degrees);co,si=math.cos(a),math.sin(a)
                        if axis=='x':y,z=co*y-si*z,si*y+co*z
                        elif axis=='y':x,z=co*x+si*z,-si*x+co*z
                        else:x,y=co*x-si*y,si*x+co*y
                    points.add((round(x+m.m_Offset.x,4),round(y+m.m_Offset.y,4)))
            self.assertEqual(points,socket,'MCU header mismatch: wrong end, mirror or model-origin offset')

    def test_mcu_models_are_registered_to_header_datums_and_explicit_assumed_gap(self):
        models=list(self.parts['U1'].Models())
        self.assertEqual(len(models),2)
        for m in models:
            self.assertEqual(m.m_Filename,'${KIPRJMOD}/../cad/local-models/nice_nano_v2.step')
            self.assertAlmostEqual(m.m_Offset.y,1.16)
        self.assertAlmostEqual(models[0].m_Rotation.z,90)
        self.assertAlmostEqual(models[1].m_Rotation.z,90)
        self.assertTrue(models[0].m_Show);self.assertFalse(models[1].m_Show)
        self.assertAlmostEqual(models[0].m_Rotation.x,180)
        self.assertAlmostEqual(models[0].m_Offset.z,7.4)
        self.assertAlmostEqual(models[1].m_Offset.z,-9.0)


if __name__=='__main__':unittest.main()
