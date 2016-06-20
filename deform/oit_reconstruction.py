# Copyright 2014-2016 The ODL development group
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

"""
Example of shape-based image reconstruction
using optimal information transformation.
"""

# Initial setup
import numpy as np
import numba
import matplotlib.pyplot as plt
import time
import ddmatch
from odl.operator.operator import Operator
import odl


def padded_ft_op(space, padding_size):
    """Create zero-padding fft setting

    Parameters
    ----------
    space : the space needs to do FT
    padding_size : the percent for zero padding
    """
    padding_op = odl.ZeroPaddingOperator(
        space, [padding_size for _ in range(space.ndim)])
    shifts = [not s % 2 for s in space.shape]
    ft_op = odl.trafos.FourierTransform(
        padding_op.range, halfcomplex=False, shift=shifts)

    return ft_op * padding_op


def kernel_ft(kernel):
    """Compute the n-D Fourier transform of the discrete kernel ``K``.

    Calculate the n-D Fourier transform of the discrete kernel ``K`` on the
    image grid points {y_i} to its reciprocal points {xi_i}.

    """
    kspace = odl.ProductSpace(discr_space, discr_space.ndim)

    # Create the array of kernel values on the grid points
    discretized_kernel = kspace.element(
        [discr_space.element(kernel) for _ in range(discr_space.ndim)])
    return vectorial_ft_op(discretized_kernel)


def generate_optimized_density_match_L2_gradient_rec(image):
    s = image.shape[0]
    if (len(image.shape) != 2):
        raise(NotImplementedError('Only 2d images are allowed so far.'))
    if (image.shape[1] != s):
        raise(NotImplementedError('Only square images are allowed so far.'))
    if (image.dtype != np.float64):
        raise(NotImplementedError('Only float64 images are allowed so far.'))

    @numba.njit('void(f8,f8[:,:],f8[:,:],f8[:,:],f8[:,:],f8[:,:],f8[:,:])')
    def density_match_L2_gradient_2d_rec(sigma, dsqrtJdx, dsqrtJdy,
                                         dtmpdx, dtmpdy, doutdx, doutdy):
        for i in xrange(s):
            for j in xrange(s):
                doutdx[i, j] = sigma*dsqrtJdx[i, j] + 2. * dtmpdx[i, j]
                doutdy[i, j] = sigma*dsqrtJdy[i, j] + 2. * dtmpdy[i, j]

    return density_match_L2_gradient_2d_rec


def proj_noise(proj_data_shape, mu=0.0, sigma=0.1):
    """Produce white Gaussian noise for projections of n-D images.

       Produce white Gaussian noise for projections, with the same size
       as the number of projections.

       Parameters
       ----------
       proj_data_shape : shape of the projections
           Give the size of noise
       mu : Mean of the norm distribution
           The defalt is 0.0
       sigma : Standard deviation of the norm distribution
           The defalt is 0.1.
    """

    return np.random.normal(mu, sigma, proj_data_shape)


def SNR(signal, noise):
    """Compute the signal-to-noise ratio in dB.
    This compute::

    SNR = 10 * log10 (
        |signal - mean(signal)| / |noise - mean(noise)|)

    Parameters
    ----------
    signal : projection
    noise : white noise
    """
    if np.abs(np.asarray(noise)).sum() != 0:
        ave1 = np.sum(signal)/signal.size
        ave2 = np.sum(noise)/noise.size
        en1 = np.sqrt(np.sum((signal - ave1) * (signal - ave1)))
        en2 = np.sqrt(np.sum((noise - ave2) * (noise - ave2)))

        return 10.0 * np.log10(en1/en2)
    else:
        return float('inf')


# Kernel function
def kernel(x):
    scaled = [xi ** 2 / (2 * sigma_kernel ** 2) for xi in x]
    return np.exp(-sum(scaled))


I0name = '../ddmatch/Example3 letters/c_highres.png'
I1name = '../ddmatch/Example3 letters/i_highres.png'
# I0name = 'Example3 letters/eight.png'
# I1name = 'Example3 letters/b.png'
# I0name = 'Example3 letters/v.png'
# I1name = 'Example3 letters/j.png'
# I0name = 'Example9 letters big/V.png'
# I1name = 'Example9 letters big/J.png'
# I0name = 'Example11 skulls/handnew1.png'
# I1name = 'Example11 skulls/handnew2.png'
# I0name = 'Example8 brains/DS0002AxialSlice80.png'
# I1name = 'Example8 brains/DS0003AxialSlice80.png'

I0 = plt.imread(I0name).astype('float')
I1 = plt.imread(I1name).astype('float')

I0 = I0[::2, ::2]
I1 = I1[::2, ::2]

# Create 2-D discretization reconstruction space
# The size of the domain should be proportional to the given images
discr_space = odl.uniform_discr([-16, -16],
                                [16, 16], [128, 128],
                                dtype='float32', interp='linear')


# Create discretization space for vector field
vspace = odl.ProductSpace(discr_space, discr_space.ndim)

# FFT setting for regularization shape term, 1 means 100% padding
padding_size = 1.0
padded_ft_op = padded_ft_op(discr_space, padding_size)
vectorial_ft_op = odl.DiagonalOperator(
    *([padded_ft_op] * discr_space.ndim))


# Create the ground truth as the given image
ground_truth = discr_space.element(I0.T)

# Create the template as the given image
template = discr_space.element(I1.T)

# Compose mass-preserving operator to template
template_mass_pre = template

# Give the number of directions
num_angles = 20

# Create the uniformly distributed directions
angle_partition = odl.uniform_partition(
    0, np.pi, num_angles, nodes_on_bdry=[(True, False)])

# Create 2-D projection domain
detector_partition = odl.uniform_partition(-24, 24, 192)

# Create 2-D parallel projection geometry
geometry = odl.tomo.Parallel2dGeometry(angle_partition,
                                       detector_partition)

# Create projection data by given setting
xray_trafo_op = odl.tomo.RayTransform(discr_space, geometry, impl='astra_cuda')

# Create projection data by given setting
proj_data = xray_trafo_op(ground_truth)

# Create white Gaussian noise
noise = 20.0 * proj_data.space.element(proj_noise(proj_data.shape))

snr = SNR(proj_data, noise)

# Output the signal-to-noise ratio
print('snr = {!r}'.format(snr))

# Create noisy projection data
noise_proj_data = proj_data + noise

# Do the backprojection reconstruction
backproj = xray_trafo_op.adjoint(noise_proj_data)

density_match_L2_gradient_rec = \
    generate_optimized_density_match_L2_gradient_rec(I1)

# kernel parameter
sigma_kernel = 3.0

# Regularization parameter, should be nonnegtive
sigma = 1000e-1

# Step size for the gradient descent method
epsilon = 0.05

# Maximum iteration number
n_iter = 1000

dm = ddmatch.TwoComponentDensityMatching(source=I1, target=I0, sigma=sigma)

# Normalize the mass of template as ground truth
W1 = I1.T * np.linalg.norm(I0, 'fro')/np.linalg.norm(I1, 'fro')

# Normalized template as an element of discretization space
template = discr_space.element(W1)

# Create the memory for energy in each iteration
E = []
kE = len(E)
E = np.hstack((E, np.zeros(n_iter)))

axis = [np.linspace(
    0, I1.shape[i], I1.shape[i], endpoint=False) for i in range(I1.ndim)]
id_map = np.meshgrid(*axis)

vec_field = [np.zeros_like(I1) for _ in range(I1.ndim)]

vx = np.zeros_like(I1)
vy = np.zeros_like(I1)

tmp = list(id_map)

tmpx = dm.idx.copy()
tmpy = dm.idy.copy()

# Compute Fourier trasform of the kernel function in data matching term
ft_kernel = kernel_ft(kernel)

# Test time, set starting time
start = time.clock()

for k in xrange(n_iter):

    # OUTPUT
    E[k+kE] = (sigma*(dm.sqrtJ - 1)**2).sum()

    # STEP 1: update template_mass_pre
    template_array = np.asarray(template, dtype='float64')
    template_mass_pre_array = np.asarray(template_mass_pre,
                                         dtype='float64')
    dm.image_compose(template_array, dm.phiinvx,
                     dm.phiinvy, template_mass_pre_array)

    print(template_mass_pre_array.sum())

    template_mass_pre_array *= dm.J
    W = template_mass_pre_array
    template_mass_pre = discr_space.element(W)

    # STEP 2: compute the L2 gradient
    tmpx_op = xray_trafo_op(template_mass_pre)
    tmpx_op -= noise_proj_data

    E[k+kE] += np.asarray(tmpx_op**2).sum()

    tmpx_op = xray_trafo_op.adjoint(tmpx_op)
    tmpx_array = np.array(tmpx_op, dtype='float64')
    dm.image_gradient(tmpx_array, dm.dtmpdx, dm.dtmpdy)
    dm.dtmpdx *= W
    dm.dtmpdy *= W

    dm.image_gradient(dm.sqrtJ, dm.dsqrtJdx, dm.dsqrtJdy)

    # Compute the L2 gradient of the energy functional

    density_match_L2_gradient_rec(sigma, dm.dsqrtJdx, dm.dsqrtJdy,
                                  dm.dtmpdx, dm.dtmpdy,
                                  vx, vy)

#    #STEP 3: Solve the Poisson equation
#    fftx = np.fft.fftn(vx)
#    ffty = np.fft.fftn(vy)
#    fftx *= dm.Linv
#    ffty *= dm.Linv
#    vx[:] = -np.fft.ifftn(fftx).real
#    vy[:] = -np.fft.ifftn(ffty).real

    # SETP 3: instead by the metric in reproducing kernel Hilbert space
    vec_field = vspace.element([vx, vy])
    ft_vec_field = vectorial_ft_op(vec_field)
    vec_field_rkhs = vectorial_ft_op.inverse(ft_kernel * ft_vec_field)
    vx[:] = -vec_field_rkhs[0]
    vy[:] = -vec_field_rkhs[1]

    # STEP 4 (v = -grad E, so to compute the inverse
    # we solve \psiinv' = -epsilon*v o \psiinv)
    np.copyto(tmpx, vx)
    tmpx *= epsilon
    np.copyto(dm.psiinvx, dm.idx)
    dm.psiinvx -= tmpx
    # Compute forward phi also (only for output purposes)
    if dm.compute_phi:
        np.copyto(dm.psix, dm.idx)
        dm.psix += tmpx

    np.copyto(tmpy, vy)
    tmpy *= epsilon
    np.copyto(dm.psiinvy, dm.idy)
    dm.psiinvy -= tmpy
    # Compute forward phi also (only for output purposes)
    if dm.compute_phi:
        np.copyto(dm.psiy, dm.idy)
        dm.psiy += tmpy

    # STEP 5
    dm.diffeo_compose(dm.phiinvx, dm.phiinvy,
                      dm.psiinvx, dm.psiinvy,
                      tmpx, tmpy)
    np.copyto(dm.phiinvx, tmpx)
    np.copyto(dm.phiinvy, tmpy)
    # Compute forward phi also (only for output purposes)
    if dm.compute_phi:
        dm.diffeo_compose(dm.phix, dm.phiy, dm.psix, dm.psiy, tmpx, tmpy)
        np.copyto(dm.phix, tmpx)
        np.copyto(dm.phiy, tmpy)

    # STEP 6
    dm.image_compose(dm.J, dm.psiinvx, dm.psiinvy, dm.sqrtJ)
    np.copyto(dm.J, dm.sqrtJ)
    dm.divergence(vx, vy, dm.divv)
    dm.divv *= -epsilon
    np.exp(dm.divv, out=dm.sqrtJ)
    dm.J *= dm.sqrtJ
    np.sqrt(dm.J, out=dm.sqrtJ)

# Test time, set end time
end = time.clock()

# Output the computational time
print(end - start)

W = W.T
dm.J = dm.J.T
dm.phiinvx, dm.phiinvy = dm.phiinvy, dm.phiinvx
backproj = np.asarray(backproj)
backproj = backproj.T

dm.template_mass_pre = discr_space.element(dm.W.T)
rec_proj_data = xray_trafo_op(template_mass_pre)

plt.figure(1, figsize=(28, 28))
plt.clf()

plt.subplot(3, 3, 1)
plt.imshow(I0, cmap='bone', vmin=dm.I0.min(), vmax=I0.max())
plt.colorbar()
plt.title('Ground truth')

plt.subplot(3, 3, 2)
plt.imshow(I1, cmap='bone', vmin=dm.I1.min(), vmax=I1.max())
plt.colorbar()
plt.title('Template')

plt.subplot(3, 3, 3)
plt.imshow(backproj, cmap='bone', vmin=backproj.min(), vmax=backproj.max())
plt.colorbar()
plt.title('Backprojection')

plt.subplot(3, 3, 4)
# plt.imshow(dm.W**2, cmap='bone', vmin=dm.I0.min(), vmax=dm.I0.max())
plt.imshow(W, cmap='bone', vmin=I1.min(), vmax=I1.max())
plt.colorbar()
plt.title('Reconstructed image by {!r} directions'.format(num_angles))
# plt.title('Warped image')

jac_ax = plt.subplot(3, 3, 5)
mycmap = 'PiYG'
# mycmap = 'Spectral'
# mycmap = 'PRGn'
# mycmap = 'BrBG'
plt.imshow(dm.J, cmap=mycmap, vmin=dm.J.min(), vmax=1.+(1.-dm.J.min()))
plt.gca().set_autoscalex_on(False)
plt.gca().set_autoscaley_on(False)
# plot_warp(dm.phiinvx, dm.phiinvy, downsample=8)
jac_colorbar = plt.colorbar()
plt.title('Jacobian')

plt.subplot(3, 3, 6)
ddmatch.plot_warp(dm.phiinvx, dm.phiinvy, downsample=4)
plt.axis('equal')
warplim = [dm.phiinvx.min(), dm.phiinvx.max(),
           dm.phiinvy.min(), dm.phiinvy.max()]
warplim[0] = min(warplim[0], warplim[2])
warplim[2] = warplim[0]
warplim[1] = max(warplim[1], warplim[3])
warplim[3] = warplim[1]

plt.axis(warplim)
# plt.axis('off')
plt.gca().invert_yaxis()
plt.gca().set_aspect('equal')
plt.title('Warp')

plt.subplot(3, 3, 7)
plt.title('stepsize = {!r}, $\sigma$ = {!r}, $K_p$ = {!r}'.format(epsilon, sigma, sigma_kernel))
plt.plot(E)
plt.ylabel('Energy')
# plt.gca().axes.yaxis.set_ticklabels(['0']+['']*8)
plt.gca().axes.yaxis.set_ticklabels([])
plt.grid(True)

plt.subplot(3, 3, 8)
plt.plot(np.asarray(proj_data)[0], 'b', np.asarray(noise_proj_data)[0], 'r')
plt.title('Theta=0, blue: truth_data, red: noisy_data, SNR = {:.3}'.format(snr))
plt.gca().axes.yaxis.set_ticklabels([])
plt.axis([0, 191, -17, 32])

plt.subplot(3, 3, 9)
plt.plot(np.asarray(proj_data)[0], 'b', np.asarray(rec_proj_data)[0], 'r')
plt.title('Theta=0, blue: truth_data, red: rec result')
plt.gca().axes.yaxis.set_ticklabels([])
plt.axis([0, 191, -17, 32])
