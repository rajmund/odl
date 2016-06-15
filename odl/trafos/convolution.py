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

"""Operators based on (integral) transformations."""

# Imports for common Python 2/3 codebase
from __future__ import print_function, division, absolute_import
from future import standard_library
standard_library.install_aliases()
from builtins import super

import numpy as np
import scipy.signal as signal

from odl.discr.discr_ops import Resampling
from odl.discr.lp_discr import (
    DiscreteLp, DiscreteLpVector, uniform_discr, uniform_discr_fromdiscr)
from odl.operator.operator import Operator
from odl.space.ntuples import Ntuples
from odl.space.cu_ntuples import CudaNtuples
from odl.set.sets import ComplexNumbers
from odl.trafos.fourier import FourierTransform
from odl.util.normalize import normalized_scalar_param_list


__all__ = ('Convolution', 'FourierSpaceConvolution', 'RealSpaceConvolution')


_REAL_CONV_SUPPORTED_IMPL = ('scipy_convolve',)
_FOURIER_CONV_SUPPORTED_IMPL = ('default_ft', 'pyfftw_ft')
_FOURIER_CONV_SUPPORTED_KER_MODES = ('real', 'ft', 'ft_hc')


class Convolution(Operator):
    pass


class FourierSpaceConvolution(Convolution):

    """Discretization of the convolution integral as an operator.

    This operator implements a discrete approximation to the continuous
    convolution with a fixed kernel. It supports real-space and
    Fourier based back-ends.
    """

    def __init__(self, dom, kernel, ran=None, **kwargs):
        """Initialize a new instance.

        Parameters
        ----------
        dom : `DiscreteLp`
            Domain of the operator
        ran : `DiscreteLp`, optional
            Range of the operator, by default the same as ``dom``
        kernel :
            The kernel can be specified in several ways, depending on
            the choice of ``impl``:

            domain `element-like` : The object is interpreted as the
            real-space kernel representation (mode ``'real'``).
            Valid for ``impl``: ``'numpy_ft', 'pyfftw_ft',
            'scipy_convolve'``

            `element-like` for the range of `FourierTransform` defined
            on ``dom`` : The object is interpreted as the Fourier
            transform of a real-space kernel (mode ``ft`` or ``'ft_hc'``).
            The correct space can be calculated with `reciprocal_space`.
            Valid for ``impl``: ``'default_ft', 'pyfftw_ft'``

            `array-like`, arbitrary length : The object is interpreted as
            real-space kernel (mode ``'real'``) and can be shorter than
            the convolved function.
            Valid for ``impl``: ``'scipy_convolve'``

        kernel_mode : {'real', 'ft', 'ft_hc'}, optional
            How the provided kernel is to be interpreted. If not
            provided, the kernel is tried to be converted into an element
            of ``dom`` or a "sliced" version of it according to ``axes``.

            'real' : element of ``dom`` (default)

            'ft' : function in the range of the Fourier transform

            'ft_hc' : function in the range of the half-complex
            (real-to-complex) Fourier transform

        impl : `str`, optional
            Implementation of the convolution. Available options are:

            'scipy_convolve': Real-space convolution using
            `scipy.signal.convolve` (default, fast for short kernels)

            'default_ft' : Fourier transform using the default FFT
            implementation

            'pyfftw_ft' : Fourier transform using pyFFTW (faster than
            the default FT)

        axes : sequence of `int`, optional
            Dimensions in which to convolve. Default: all axes

        scale : `bool`, optional
            If `True`, scale the discrete convolution such that it
            corresponds to a continuous convolution. The scaling
            factor is ``2*pi ** (ndim/2)`` for FT-based convolutions
            and the `DiscreteLp.cell_volume` for the SciPy
            implementation.
            Default: `True`

        kwargs :
            Extra arguments are passed to the transform when the
            kernel FT is calculated.

        See also
        --------
        FourierTransform : discretization of the continuous FT
        scipy.signal.convolve : real-space convolution

        Notes
        -----
        - For Fourier-based convolutions, only the Fourier transform
          of the kernel is stored. The real-space kernel can be retrieved
          with ``conv.transform.inverse(conv.kernel_ft)`` if ``conv``
          is the convolution operator.

        - The continuous convolution of two functions
          :math:`f` and :math:`g` defined on :math:`\mathbb{R^d}` is

              :math:`[f \\ast g](x) =
              \int_{\mathbb{R^d}} f(x - y) g(y) \mathrm{d}y`.

          With the help of the Fourier transform, this operation can be
          expressed as a multiplication,

              :math:`\\big[\mathcal{F}(f \\ast g)\\big](\\xi)
              = (2\pi)^{\\frac{d}{2}}\,
              \\big[\mathcal{F}(f)\\big](\\xi) \cdot
              \\big[\mathcal{F}(g)\\big](\\xi)`.

          This implementation covers the case of a fixed convolution
          kernel :math:`k`, i.e. the linear operator

              :math:`\\big[\mathcal{C}_k(f)\\big](x) = [k \\ast f](x)`

          mapping the Lebesgue space :math:`L^p(\mathbb{R^d})` to itself
          (provided :math:`k \\in L^1(\mathbb{R^d})`), according to
          `Young's inequality for convolutions
          <https://en.wikipedia.org/wiki/Young's_inequality#\
Young.27s_inequality_for_convolutions>`_.
        """
        # Basic checks
        if not isinstance(dom, DiscreteLp):
            raise TypeError('domain {!r} is not a DiscreteLp instance.'
                            ''.format(dom))

        if ran is not None:
            # TODO
            raise NotImplementedError('custom range not implemented')
        else:
            ran = dom

        super().__init__(dom, ran, linear=True)

        # Handle kernel mode and impl
        impl = kwargs.pop('impl', 'default_ft')
        impl, impl_in = str(impl).lower(), impl
        if impl not in _CONV_SUPPORTED_IMPL:
            raise ValueError("implementation '{}' not understood."
                             ''.format(impl_in))
        self._impl = impl

        ker_mode = kwargs.pop('kernel_mode', 'real')
        ker_mode, ker_mode_in = str(ker_mode).lower(), ker_mode
        if ker_mode not in _CONV_SUPPORTED_KER_MODES:
            raise ValueError("kernel mode '{}' not understood."
                             ''.format(ker_mode_in))

        self._kernel_mode = ker_mode

        use_own_ft = (self.impl in ('default_ft', 'pyfftw_ft'))
        if not use_own_ft and self.kernel_mode != 'real':
            raise ValueError("kernel mode 'real' is required for impl "
                             "{}.".format(impl_in))

        self._axes = list(kwargs.pop('axes', (range(self.domain.ndim))))
        if ker_mode == 'real':
            halfcomplex = True  # efficient
        else:
            halfcomplex = ker_mode.endswith('hc')

        if use_own_ft:
            fft_impl = self.impl.split('_')[0]
            self._transform = FourierTransform(
                self.domain, axes=self.axes, halfcomplex=halfcomplex,
                impl=fft_impl)
        else:
            self._transform = None

        scale = kwargs.pop('scale', True)

        # TODO: handle case if axes are given, but the kernel is the same
        # for each point along the other axes
        if ker_mode == 'real':
            # Kernel given as real space element
            if use_own_ft:
                self._kernel = None
                self._kernel_transform = self.transform(kernel, **kwargs)
                if scale:
                    self._kernel_transform *= (np.sqrt(2 * np.pi) **
                                               self.domain.ndim)
            else:
                if not self.domain.partition.is_regular:
                    raise NotImplementedError(
                        'real-space convolution not implemented for '
                        'irregular sampling.')
                try:
                    # Function or other element-like as input. All axes
                    # must be used, otherwise we get an error.
                    # TODO: make a zero-centered space by default and
                    # adapt the range otherwise
                    self._kernel = self._kernel_elem(
                        self.domain.element(kernel).asarray(), self.axes)
                except (TypeError, ValueError):
                    # Got an array-like, axes can be used
                    self._kernel = self._kernel_elem(kernel, self.axes)
                finally:
                    self._kernel_transform = None
                    if scale:
                        self._kernel *= self.domain.cell_volume
        else:
            # Kernel given as Fourier space element
            self._kernel = None
            self._kernel_transform = self.transform.range.element(kernel)
            if scale:
                self._kernel_transform *= (np.sqrt(2 * np.pi) **
                                           self.domain.ndim)

    def _kernel_elem(self, kernel, axes):
        """Return kernel with adapted shape for real space convolution."""
        kernel = np.asarray(kernel)
        extra_dims = self.domain.ndim - kernel.ndim

        if extra_dims == 0:
            return self.domain.element(kernel)
        else:
            if len(axes) != extra_dims:
                raise ValueError('kernel dim {} + number of axes {} '
                                 '!= space dimension {}.'
                                 ''.format(kernel.ndim, len(axes),
                                           self.domain.ndim))

            # Sparse kernel (less dimensions), blow up
            slc = [None] * self.domain.ndim
            for ax in axes:
                slc[ax] = slice(None)

            kernel = kernel[slc]
            # Assuming uniform discretization
            min_corner = -self.domain.cell_sides * self.domain.shape / 2
            max_corner = self.domain.cell_sides * self.domain.shape / 2
            if isinstance(self.domain.dspace, Ntuples):
                impl = 'numpy'
            elif isinstance(self.domain.dspace, CudaNtuples):
                impl = 'cuda'
            else:
                raise RuntimeError

            space = uniform_discr(min_corner, max_corner, kernel.shape,
                                  self.domain.exponent, self.domain.interp,
                                  impl, dtype=self.domain.dspace.dtype,
                                  order=self.domain.order,
                                  weighting=self.domain.weighting)
            return space.element(kernel)

    @property
    def impl(self):
        """Implementation of this operator."""
        return self._impl

    @property
    def kernel_mode(self):
        """The way in which the kernel is specified."""
        return self._kernel_mode

    @property
    def transform(self):
        """Fourier transform operator back-end if used, else `None`."""
        return self._transform

    @property
    def axes(self):
        """Axes along which the convolution is taken."""
        return self._axes

    @property
    def kernel(self):
        """Real-space kernel if used, else `None`.

        Note that this is the scaled version ``kernel * cell_volume``
        if ``scale=True`` was specified. Scaling here is more efficient
        than scaling the result.
        """
        return self._kernel

    @property
    def kernel_space(self):
        """Space of the convolution kernel."""
        return getattr(self.kernel, 'space', None)

    @property
    def kernel_transform(self):
        """Fourier-space kernel if used, else `None`.

        Note that this is the scaled version
        ``kernel_ft * (2*pi) ** (ndim/2)`` of the FT of the input
        kernel if ``scale=True`` was specified. Scaling here is more
        efficient than scaling the result.
        """
        return self._kernel_transform

    def _call(self, x, out, **kwargs):
        """Implement ``self(x, out[, **kwargs])``.

        Keyword arguments are passed on to the transform.
        """
        if self.kernel is not None:
            # Scipy based convolution
            out[:] = signal.convolve(x, self.kernel, mode='same')
        elif self.kernel_transform is not None:
            # Convolution based on our own transforms
            if self.domain.field == ComplexNumbers():
                # Use out as a temporary, has the same size
                # TODO: won't work for CUDA
                tmp = self.transform.range.element(out.asarray())
            else:
                # No temporary since out has reduced size (halfcomplex)
                tmp = None

            x_trafo = self.transform(x, out=tmp, **kwargs)
            x_trafo *= self.kernel_transform

            self.transform.inverse(x_trafo, out=out, **kwargs)
        else:
            raise RuntimeError('both kernel and kernel_transform are None.')

    def _adj_kernel(self, kernel, axes):
        """Return adjoint kernel with adapted shape."""
        kernel = np.asarray(kernel).conj()
        extra_dims = self.domain.ndim - kernel.ndim

        if extra_dims == 0:
            slc = [slice(None, None, -1)] * self.domain.ndim
            return kernel[slc]
        else:
            if len(axes) != extra_dims:
                raise ValueError('kernel dim ({}) + number of axes ({}) '
                                 'does not add up to the space dimension '
                                 '({}).'.format(kernel.ndim, len(axes),
                                                self.domain.ndim))

            # Sparse kernel (less dimensions), blow up
            slc = [None] * self.domain.ndim
            for ax in axes:
                slc[ax] = slice(None, None, -1)
            return kernel[slc]

    @property
    def adjoint(self):
        """Adjoint operator."""
        if self.kernel is not None:
            # TODO: this could be expensive. Move to init?
            adj_kernel = self._adj_kernel(self.kernel, self.axes)
            return Convolution(dom=self.domain,
                               kernel=adj_kernel, kernel_mode='real',
                               impl=self.impl, axes=self.axes)

        elif self.kernel_transform is not None:
            # TODO: this could be expensive. Move to init?
            adj_kernel_ft = self.kernel_transform.conj()

            if self.transform.halfcomplex:
                kernel_mode = 'ft_hc'
            else:
                kernel_mode = 'ft'
            return Convolution(dom=self.domain,
                               kernel=adj_kernel_ft, kernel_mode=kernel_mode,
                               impl=self.impl, axes=self.axes)
        else:
            raise RuntimeError('both kernel and kernel_transform are None.')


class RealSpaceConvolution(Convolution):

    """Convolution implemented in real space."""

    def __init__(self, domain, kernel, range=None, **kwargs):
        """Initialize a new instance.

        Parameters
        ----------
        domain : `DiscreteLp`
            Domain of the operator
        kernel :
            The kernel can be specified in several ways, depending on
            the choice of ``impl``:

            `DiscreteLpVector` :
            Valid for ``impl``: ``'scipy_convolve'``

            `array-like`, arbitrary shape : The object is interpreted as
            real-space kernel (mode ``'real'``) and can be differently
            sized than the convolved function. It is assumed to be an
            element of a space with same `DiscreteLp.cell_sides` as
            ``domain``. Note that the ``scipy_convolve`` back-end does
            not allow the kernel to be larger.
            Valid for ``impl``: ``'scipy_convolve'``

        range : `DiscreteLp`, optional
            Range of the operator. By default, the range is calculated
            from the kernel.
            Note: custom range is currently not supported.

        impl : string, optional
            Implementation of the convolution. Available options are:

            'scipy_convolve': Real-space convolution using
            `scipy.signal.convolve` (default, fast for short kernels)

        scale : `bool`, optional
            If `True`, scale the discrete convolution with
            `DiscreteLp.cell_volume`, such that it
            corresponds to a continuous convolution.
            Default: `True`

        resample : string or sequence of strings
            If ``kernel`` and ``domain`` have different cell sizes,
            this option defines the behavior of the evaluation. The
            following values can be given (per axis in the case of a
            sequence):

            'down' : Use the larger one of the two cell sizes (default).

            'up' : Use the smaller one of the two cell sizes. Note that
            this can be computationally expensive.

        kernel_kwargs : dict, optional
            Keyword arguments passed to the call of the kernel function
            if given as a callable.

        See also
        --------
        scipy.signal.convolve : real-space convolution

        Notes
        -----
        - The continuous convolution of two functions
          :math:`f` and :math:`g` defined on :math:`\mathbb{R^d}` is

              :math:`[f \\ast g](x) =
              \int_{\mathbb{R^d}} f(x - y) g(y) \mathrm{d}y`.

          This implementation covers the case of a fixed convolution
          kernel :math:`k`, i.e. the linear operator :math:`\mathcal{C}_k`
          given by

              :math:`\mathcal{C}_k(f): x \mapsto [k \\ast f](x)`.

        - If the convolution kernel :math:`k` is defined on a rectangular
          domain :math:`\Omega_0` with midpoint :math:`m_0`, then the
          convolution :math:`k \\ast f` of a function
          :math:`f:\Omega \\to \mathbb{R}` with :math:`k` has a support
          that is a superset of :math:`\Omega + m_0`. Therefore, we
          choose to keep the size of the domain and take
          :math:`\Omega + m_0` as the domain of definition of functions
          in the range of the convolution operator.

          In fact, the support of the convolution is contained in the
          `Minkowski sum
          <https://en.wikipedia.org/wiki/Minkowski_addition>`_
          :math:`\Omega + \Omega_0`.

          For example, if :math:`\Omega = [0, 5]` and
          :math:`\Omega_0 = [1, 3]`, i.e. :math:`m_0 = 2`, then
          :math:`\Omega + \Omega_0 = [1, 8]`. However, we choose the
          shifted interval :math:`\Omega + m_0 = [2, 7]` for the range
          of the convolution since it contains the "main mass" of the
          result.
        """
        # Basic checks
        if not isinstance(domain, DiscreteLp):
            raise TypeError('domain {!r} is not a DiscreteLp instance'
                            ''.format(domain))
        if not domain.partition.is_regular:
            raise NotImplementedError('irregular sampling not supported')

        if range is not None:
            # TODO
            raise NotImplementedError('custom range not implemented')
        else:
            kernel_kwargs = kwargs.pop('kernel_kwargs', {})
            self._kernel, range = self._compute_kernel_and_range(
                kernel, domain, kernel_kwargs)

        super().__init__(domain, range, linear=True)

        # Handle kernel mode and impl
        impl = kwargs.pop('impl', 'scipy_convolve')
        impl, impl_in = str(impl).lower(), impl
        if impl not in _REAL_CONV_SUPPORTED_IMPL:
            raise ValueError("implementation '{}' not understood"
                             ''.format(impl_in))

        self._impl = impl

        # Handle the `resample` input parameter
        resample = normalized_scalar_param_list(kwargs.pop('resample', 'down'),
                                                length=self.domain.ndim,
                                                param_conv=str)

        for i, r in enumerate(resample):
            if r.lower() not in ('up', 'down'):
                raise ValueError("in axis {}: `resample` '{}' not understood"
                                 ''.format(i, r))
            else:
                resample[i] = r.lower()

        self._resample = resample

        # Initialize resampling operators
        new_kernel_csides, new_domain_csides = self._get_resamp_csides(
            self.resample, self._kernel.space.cell_sides,
            self.domain.cell_sides)

        domain_resamp_space = uniform_discr_fromdiscr(
            self.domain, cell_sides=new_domain_csides)
        self._domain_resampling_op = Resampling(self.domain,
                                                domain_resamp_space)

        kernel_resamp_space = uniform_discr_fromdiscr(
            self._kernel.space, cell_sides=new_kernel_csides)
        self._kernel_resampling_op = Resampling(self._kernel.space,
                                                kernel_resamp_space)

        # Scale the kernel if desired
        self._kernel_scaling = np.prod(new_kernel_csides)
        self._scale = bool(kwargs.pop('scale', True))
        if self._scale:
            # Don't modify the input
            self._kernel = self._kernel * self._kernel_scaling

    @staticmethod
    def _compute_kernel_and_range(kernel, domain, kernel_kwargs):
        """Return the kernel and the operator range based on the domain.

        This helper function computes an adequate zero-centered domain
        for the kernel if necessary (i.e. if the kernel is not a
        `DiscreteLpVector`) and calculates the operator range based
        on the operator domain and the kernel space.

        Parameters
        ----------
        kernel : `DiscreteLpVector` or array-like
            Kernel of the convolution.
        domain : `DiscreteLp`
            Domain of the convolution operator.
        kernel_kwargs : dict
            Used as ``space.element(kernel, **kernel_kwargs)`` if
            ``kernel`` is callable.

        Returns
        -------
        kernel : `DiscreteLpVector`
            Element in an adequate space.
        range : `DiscreteLp`
            Range of the convolution operator.
        """
        if isinstance(kernel, DiscreteLpVector) and kernel not in domain:
            if kernel.ndim != domain.ndim:
                raise ValueError('`kernel` has dimension {}, expected {}'
                                 ''.format(kernel.ndim, domain.ndim))
            # The kernel lies in a different space. We first zero-center
            # its domain and set the range to the domain shifted by
            # the the midpoint of the kernel domain.

            # TODO: DiscreteLp.element should probably bail out if
            # kernel is a DiscreteLpVector but not in the same space
            kernel_shift = kernel.space.partition.midpoint
            range = uniform_discr_fromdiscr(
                domain, min_corner=domain.min_corner + kernel_shift)

        elif callable(kernel):
            # The kernel is a Python function or some other callable object.
            kernel = domain.element(kernel, **kernel_kwargs)
            range = domain
        else:
            try:
                # kernel is an array-like of the correct shape or an
                # element of `domain`
                kernel = domain.element(kernel)
            except (TypeError, ValueError):
                # Array-like of wrong shape -> find adequate space for the
                # kernel. Assume 0-centering and same cell size.

                # TODO: handle the case when the outer cells are of
                # different size
                kernel = np.asarray(kernel, dtype=domain.dtype)
                nsamples = kernel.shape
                extent = domain.cell_sides * nsamples
                kernel_space = uniform_discr_fromdiscr(
                    domain, min_corner=-extent / 2, max_corner=extent / 2,
                    nsamples=nsamples)
                kernel = kernel_space.element(kernel)

            range = domain

        return kernel, range

    @staticmethod
    def _get_resamp_csides(resample, ker_csides, dom_csides):
        """Return cell sides for kernel and domain resampling."""
        new_ker_csides = []
        new_dom_csides = []
        for resamp, ks, ds in zip(resample, ker_csides, dom_csides):

            if np.isclose(ks, ds):
                # Keep old if both csides are the same
                new_ker_csides.append(ks)
                new_dom_csides.append(ds)
            else:
                # Pick the coarser one if 'down' or the finer one if 'up'
                if ((ks < ds and resamp == 'up') or
                        (ks > ds and resamp == 'down')):
                    new_ker_csides.append(ks)
                    new_dom_csides.append(ks)
                else:
                    new_ker_csides.append(ds)
                    new_dom_csides.append(ds)

        return new_ker_csides, new_dom_csides

    @property
    def impl(self):
        """Implementation of this operator."""
        return self._impl

    @property
    def resample(self):
        """Resampling used during evaluation."""
        return self._resample

    def kernel(self):
        """Return the real-space kernel of this convolution operator.

        Note that internally, the scaled kernel is stored if
        ``scale=True`` was chosen during initialization, i.e. calculating
        the original kernel requires to reverse the scaling.
        Otherwise, the original unscaled kernel is returned.
        """
        if self._scale:
            return self._kernel / self._kernel_scaling
        else:
            return self._kernel

    def _call(self, x):
        """Implement ``self(x)``."""
        if np.allclose(self._kernel.space.cell_sides, self.domain.cell_sides):
            # No resampling needed
            print('no resampling')

            # According to the documentation of scipy.signal.convolve, we
            # would need to switch order of x and kernel since `convolve`
            # expects the larger array first. However, this does not seem
            # to be needed.
            return signal.convolve(x, self._kernel, mode='same')
        else:
            if self.domain != self._domain_resampling_op.range:
                # Only resample if necessary
                print('resample function')
                x = self._domain_resampling_op(x)

            if self._kernel.space != self._kernel_resampling_op.range:
                print('resample kernel')
                kernel = self._kernel_resampling_op(self._kernel)
            else:
                kernel = self._kernel

            conv = signal.convolve(x, kernel, mode='same')
            return self._domain_resampling_op.inverse(conv)


if __name__ == '__main__':
    # pylint: disable=wrong-import-position
    from odl.util.testutils import run_doctests
    run_doctests()
