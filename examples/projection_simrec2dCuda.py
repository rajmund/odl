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

# pylint: disable=abstract-method

# Imports for common Python 2/3 codebase
from __future__ import print_function, division, absolute_import
from future import standard_library
standard_library.install_aliases()
from builtins import super

from math import sin, cos
import numpy as np

import odl
import SimRec2DPy as SR
import matplotlib.pyplot as plt


class CudaProjection(odl.LinearOperator):
    def __init__(self, volumeOrigin, voxelSize, nVoxels, nPixels, stepSize,
                 sourcePosition, detectorOrigin, pixelDirection,
                 domain, range_):
        super().__init__(domain, range_)
        self.sourcePosition = sourcePosition
        self.detectorOrigin = detectorOrigin
        self.pixelDirection = pixelDirection
        self.forward = SR.SRPyCuda.CudaForwardProjector(
            nVoxels, volumeOrigin, voxelSize, nPixels, stepSize)
        self._adjoint = CudaBackProjector(
            volumeOrigin, voxelSize, nVoxels, nPixels, stepSize,
            sourcePosition, detectorOrigin, pixelDirection, range_, domain)

    def _apply(self, volume, projection):
        self.forward.setData(volume.ntuple.data_ptr)
        self.forward.project(self.sourcePosition, self.detectorOrigin,
                             self.pixelDirection, projection.ntuple.data_ptr)

    @property
    def adjoint(self):
        return self._adjoint


class CudaBackProjector(odl.LinearOperator):
    def __init__(self, volumeOrigin, voxelSize, nVoxels, nPixels, stepSize,
                 sourcePosition, detectorOrigin, pixelDirection,
                 domain, range):
        super().__init__(domain, range)
        self.sourcePosition = sourcePosition
        self.detectorOrigin = detectorOrigin
        self.pixelDirection = pixelDirection
        self.back = SR.SRPyCuda.CudaBackProjector(
            nVoxels, volumeOrigin, voxelSize, nPixels, stepSize)

    def _apply(self, projection, volume):
        self.back.backProject(self.sourcePosition, self.detectorOrigin,
                              self.pixelDirection, projection.ntuple.data_ptr,
                              volume.ntuple.data_ptr)


# Set geometry parameters
volumeSize = np.array([20.0, 20.0])
volumeOrigin = -volumeSize/2.0

detectorSize = 50.0
detectorOrigin = -detectorSize/2.0

sourceAxisDistance = 20.0
detectorAxisDistance = 20.0

# Discretization parameters
nVoxels = np.array([500, 400])
nPixels = 400
nProjection = 500

# Scale factors
voxelSize = volumeSize/nVoxels
pixelSize = detectorSize/nPixels
stepSize = voxelSize.max()/20.0

# Define projection geometries
theta = 0.0
x0 = np.array([cos(theta), sin(theta)])
y0 = np.array([-sin(theta), cos(theta)])

sourcePosition = -sourceAxisDistance * x0
detectorOrigin = detectorAxisDistance * x0 + detectorOrigin * y0
pixelDirection = y0 * pixelSize

dataSpace = odl.L2(odl.Interval(0, 1))
dataDisc = odl.l2_uniform_discretization(dataSpace, nPixels, impl='cuda')

reconSpace = odl.L2(odl.Rectangle((0, 0), (1, 1)))
reconDisc = odl.l2_uniform_discretization(reconSpace, nVoxels, impl='cuda')

# Create a phantom
phantom = SR.SRPyUtils.phantom(nVoxels)
plt.imshow(phantom)
phantomVec = reconDisc.element(phantom.flatten())

projector = CudaProjection(volumeOrigin, voxelSize, nVoxels, nPixels, stepSize,
                           sourcePosition, detectorOrigin, pixelDirection,
                           reconDisc, dataDisc)

result = dataDisc.element()
projector(phantomVec, result)

plt.figure()
plt.plot(result[:])

backprojected = reconDisc.element()
projector.adjoint(result, backprojected)

plt.figure()
plt.imshow(backprojected.asarray().reshape(nVoxels))
plt.show()
