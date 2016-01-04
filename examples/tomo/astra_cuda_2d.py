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

"""Examples using the ASTRA CUDA."""

# pylint: disable=invalid-name,no-name-in-module

from __future__ import print_function, division, absolute_import
import os.path as pth
from future import standard_library
standard_library.install_aliases()

# External
import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as plt
import numpy as np

# Internal
from odl import (Interval, FunctionSpace, uniform_discr,
                 uniform_discr_fromspace, uniform_sampling)
from odl.tomo import (Parallel2dGeometry, FanFlatGeometry,
                      astra_cuda_forward_projector_call,
                      astra_cuda_backward_projector_call)


def save_slice(data, name):
    """Save image.

    Parameters
    ----------
    data : `DiscreteLp`
    name : `str`
    """
    path = pth.join(pth.join(pth.expanduser("~"), 'data'), 'astra')

    filename = '{}.png'.format(name.replace(' ', '_'))
    path = pth.join(path, filename)

    data.show('imshow', saveto=path, title='{} [:,:]'.format(name))

    plt.close()

# Create `DiscreteLp` space for volume data
vol_shape = (100, 110)
discr_vol_space = uniform_discr([-1, -1.1], [1, 1.1], vol_shape,
                                dtype='float32')
# Phantom data
phantom = np.zeros(vol_shape)
phantom[20:30, 20:30] = 1

# Create an element in the volume space
discr_vol_data = discr_vol_space.element(phantom)

save_slice(discr_vol_data, 'phantom 2d cuda')

# Angles
angle_intvl = Interval(0, 2 * np.pi)
angle_grid = uniform_sampling(angle_intvl, 180)

# Detector
dparams = Interval(-2, 2)
det_grid = uniform_sampling(dparams, 100)

# Distances for fanflat geometry
src_rad = 1000
det_rad = 100

# Create geometry instances
geom_p2d = Parallel2dGeometry(angle_intvl, dparams, angle_grid, det_grid)
geom_ff = FanFlatGeometry(angle_intvl, dparams, src_rad, det_rad,
                          angle_grid, det_grid)

# Projection space
proj_space = FunctionSpace(geom_p2d.params)

# `DiscreteLp` projection space
proj_shape = (angle_grid.ntotal, det_grid.ntotal)
discr_proj_space = uniform_discr_fromspace(proj_space, proj_shape,
                                           dtype='float32')

# Forward and back projections

# PARALLEL 2D: forward
proj_data_p2d = astra_cuda_forward_projector_call(discr_vol_data, geom_p2d,
                                                 discr_proj_space)
save_slice(proj_data_p2d, 'forward parallel 2d cuda')

# PARALLEL 2D: backward
reco_data_p2d = astra_cuda_backward_projector_call(proj_data_p2d, geom_p2d,
                                                  discr_vol_space)
save_slice(reco_data_p2d, 'backward parallel 2d cuda')

# Fanflat: forward
discr_vol_data = discr_vol_space.element(phantom)
proj_data_ff = astra_cuda_forward_projector_call(discr_vol_data, geom_ff,
                                                discr_proj_space)
save_slice(proj_data_ff, 'forward fanflat cuda')

# Fanflat: backward
reco_data_ff = astra_cuda_backward_projector_call(proj_data_ff, geom_ff,
                                                 discr_vol_space)
save_slice(reco_data_ff, 'backward fanflat_cuda')

