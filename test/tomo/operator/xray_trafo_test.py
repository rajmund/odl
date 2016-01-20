# Copyright 2014, 2015 The ODL development group
#
# This file is part of ODL.
#
# ODL is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ODL is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ODL.  If not, see <http://www.gnu.org/licenses/>.

"""Test for X-ray transforms."""

# Imports for common Python 2/3 codebase
from __future__ import print_function, division, absolute_import
from future import standard_library

standard_library.install_aliases()

# External
import numpy as np
import pytest

# Internal
import odl
from odl.util.testutils import almost_equal
from odl.tomo import ASTRA_CUDA_AVAILABLE
from odl.tomo.util.testutils import skip_if_no_astra_cuda

# Discrete reconstruction space
xx = 5
nn = 5
discr_vol_space3 = odl.uniform_discr([-xx] * 3, [xx] * 3, [nn] * 3,
                                     dtype='float32')
discr_vol_space2 = odl.uniform_discr([-xx] * 2, [xx] * 2, [nn] * 2,
                                     dtype='float32')

# Angle
angle_intvl = odl.Interval(0, 2 * np.pi) - np.pi/4
agrid = odl.uniform_sampling(angle_intvl, 4)

# Detector
yy = 11
mm = 11
dparams1 = odl.Interval(-yy, yy)
dgrid1 = odl.uniform_sampling(dparams1, mm)
dparams2 = odl.Rectangle([-yy, -yy], [yy, yy])
dgrid2 = odl.uniform_sampling(dparams2, [mm] * 2)

# Distances
src_radius = 1000
det_radius = 500

@skip_if_no_astra_cuda
def test_xray_trafo_parallel2d():
    """2D parallel-beam discrete X-ray transform with ASTRA CUDA."""

    # `DiscreteLp` volume space
    discr_vol_space2 = odl.uniform_discr([-5] * 2, [5] * 2, [5] * 2,
                                         dtype='float32')

    angle_intvl = odl.Interval(0, 2 * np.pi) - np.pi / 4
    agrid = odl.uniform_sampling(angle_intvl, 4)

    dparams1 = odl.Interval(-11, 11)
    dgrid1 = odl.uniform_sampling(dparams1, 11)
    # dparams1 = odl.Interval(-10.5, 10.5)
    # dgrid1 = odl.uniform_sampling(dparams1, 21)


    # Geometry
    geom = odl.tomo.Parallel2dGeometry(angle_intvl, dparams1, agrid, dgrid1)

    # X-ray transform
    A = odl.tomo.DiscreteXrayTransform(discr_vol_space2, geom,
                                       backend='astra_cuda')

    # Domain element
    f = A.domain.one()

    # Forward projection
    Af = A(f) / float(A.range.grid.stride[1])

    # Range element
    g = A.range.one()

    # Back projection
    Adg = A.adjoint(g)

    # Scaling
    # Af *= float(dgrid1.stride)
    # Adg *= discr_vol_space2.grid.cell_volume
    # Af = A(f) / float(A.range.grid.stride[1])

    inner_proj = Af.inner(g)
    inner_vol = f.inner(Adg)
    r = inner_vol / inner_proj  # / float(agrid.stride)

    print('\n')
    print('angle grid = {}'.format(agrid.points().transpose() / np.pi))
    print('vol stride :', discr_vol_space2.grid.stride)
    print('proj stride:', geom.grid.stride)
    print('inner vol :', inner_vol)
    print('inner proj:', inner_proj)
    print('ratios: {:.4f}, {:.4f}'.format(r, 1 / r))
    print('ratios-1: {:.4f}, {:.4f}'.format(abs(r - 1), abs(1 / r - 1)))

    # print(dgrid1.points())
    print(Af.asarray()[0])
    print(Adg.asarray()/float(agrid.stride))


@skip_if_no_astra_cuda
def test_xray_trafo_fanflat():
    """2D parallel-beam discrete X-ray transform with ASTRA CUDA."""

    # Distances
    src_radius = 100000
    det_radius = 10

    # `DiscreteLp` volume space
    discr_vol_space2 = odl.uniform_discr([-5] * 2, [5] * 2, [5] * 2,
                                         dtype='float32')

    angle_intvl = odl.Interval(0, 2 * np.pi) - np.pi/4
    agrid = odl.uniform_sampling(angle_intvl, 4)

    dparams1 = odl.Interval(-10.5, 10.5)
    dgrid1 = odl.uniform_sampling(dparams1, 21)

    # Geometry
    geom = odl.tomo.FanFlatGeometry(angle_intvl, dparams1, src_radius,
                                    det_radius, agrid, dgrid1)

    # X-ray transform
    A = odl.tomo.DiscreteXrayTransform(discr_vol_space2, geom,
                                       backend='astra_cpu')

    # Domain element
    f = A.domain.one()

    # Forward projection
    Af = A(f) * float(dgrid1.stride)

    # Range element
    g = A.range.one()

    # Back projection
    Adg = A.adjoint(g)

    # Scaling
    # Af *= float(dgrid1.stride)
    # Adg *= discr_vol_space2.grid.cell_volume
    # Af = A(f) / float(A.range.grid.stride[1])

    inner_proj = Af.inner(g)
    inner_vol = f.inner(Adg)
    r = inner_vol / inner_proj # / float(agrid.stride)

    print('\n')
    print('angle grid = {}'.format(agrid.points().transpose()/np.pi))
    print('vol stride :', discr_vol_space2.grid.stride)
    print('proj stride:', geom.grid.stride)
    print('mag = ', (src_radius+det_radius)/src_radius)
    print('inner vol :', inner_vol)
    print('inner proj:', inner_proj)
    print('ratios: {:.4f}, {:.4f}'.format(r, 1 / r))
    print('ratios-1: {:.4f}, {:.4f}'.format(abs(r - 1), abs(1 / r - 1)))

    # print(dgrid1.points())
    print(Af.asarray()[0])


@skip_if_no_astra_cuda
def test_xray_trafo_parallel3d():
    """3D parallel-beam discrete X-ray transform with ASTRA CUDA."""

    # Geometry
    geom = odl.tomo.Parallel3dGeometry(angle_intvl, dparams2, agrid, dgrid2)

    # X-ray transform
    A = odl.tomo.DiscreteXrayTransform(discr_vol_space3, geom,
                                       backend='astra_cuda')

    # Domain element
    f = A.domain.one()

    # Forward projection
    Af = A(f)

    # Range element
    g = A.range.one()

    # Back projection
    Adg = A.adjoint(g)

    # Assure not to use unit cell sizes
    assert discr_vol_space3.grid.cell_volume != 1
    assert geom.grid.cell_volume != 1

    # Test adjoint
    assert almost_equal(Af.inner(g), f.inner(Adg), 2)

    print(discr_vol_space3.grid.stride)
    print(geom.grid.stride)
    print(Af.asarray()[0, :, np.floor(Af.shape[2]/2)])
    print(Adg.asarray()[:, :, np.round(f.shape[2]/2)]/float(agrid.stride))


@pytest.mark.skipif("not odl.tomo.ASTRA_CUDA_AVAILABLE")
def test_xray_trafo_conebeam_circular():
    """Cone-beam trafo with circular acquisition and ASTRA CUDA backend."""

    # Geometry
    geom = odl.tomo.CircularConeFlatGeometry(angle_intvl, dparams2,
                                             src_radius, det_radius,
                                             agrid, dgrid2,
                                             axis=[0, 0, 1])

    # X-ray transform
    A = odl.tomo.DiscreteXrayTransform(discr_vol_space3, geom,
                                       backend='astra_cuda')
    # Domain element
    f = A.domain.one()

    # Forward projection
    Af = A(f)

    # Range element
    g = A.range.one()

    # Back projection
    Adg = A.adjoint(g)

    # Assure not to use unit cell sizes
    assert discr_vol_space3.grid.cell_volume != 1
    assert geom.grid.cell_volume != 1

    # Test adjoint
    assert almost_equal(Af.inner(g), f.inner(Adg), 1)


# @pytest.mark.xfail  # Expected to fail since scaling of adjoint is wrong.
@skip_if_no_astra_cuda
def test_xray_trafo_conebeam_helical():
    """Cone-beam trafo with helical acquisition and ASTRA CUDA backend."""

    # Geometry
    geom = odl.tomo.HelicalConeFlatGeometry(angle_intvl, dparams2,
                                            src_radius, det_radius, pitch=2,
                                            agrid=agrid, dgrid=dgrid2,
                                            axis=[0, 0, 1])

    # X-ray transform
    A = odl.tomo.DiscreteXrayTransform(discr_vol_space3, geom,
                                       backend='astra_cuda')
    # Domain element
    f = A.domain.one()

    # Forward projection
    Af = A(f)

    # Range element
    g = A.range.one()

    # Back projection
    Adg = A.adjoint(g)

    # Assure not to use trivial pitch or cell sizes
    assert discr_vol_space3.grid.cell_volume != 1
    assert geom.grid.cell_volume != 1
    assert geom.pitch != 0

    # Test adjoint
    assert almost_equal(Af.inner(g), f.inner(Adg), 1)


if __name__ == '__main__':
    pytest.main(str(__file__.replace('\\', '/') + ' -v'))
