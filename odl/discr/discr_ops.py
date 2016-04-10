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

"""Operators defined on `DiscreteLp`."""

# Imports for common Python 2/3 codebase
from __future__ import print_function, division, absolute_import
from future import standard_library
standard_library.install_aliases()
from builtins import super

from odl.discr.lp_discr import DiscreteLp
from odl.operator.operator import Operator
from odl.space.pspace import ProductSpace
from odl.set.sets import ComplexNumbers
from odl.trafos.fourier import FourierTransform, DiscreteFourierTransform


__all__ = ('Resampling',)


class Resampling(Operator):
    """A operator that resamples a vector on another grid.

    The operator uses the underlying `Discretization.sampling` and
    `Discretization.interpolation` operators to achieve this.

    The spaces need to have the same `Discretization.uspace` in order for this
    to work. The dspace types may however be different, although performance
    may vary drastically.
    """

    def __init__(self, domain, range):
        """Initialize a Resampling.

        Parameters
        ----------
        domain : `LinearSpace`
            The space that should be cast from
        range : `LinearSpace`
            The space that should be cast to

        Examples
        --------
        Create two spaces with different number of points and create resampling
        operator.

        >>> import odl
        >>> X = odl.uniform_discr(0, 1, 3)
        >>> Y = odl.uniform_discr(0, 1, 6)
        >>> resampling = Resampling(X, Y)
        """
        if domain.uspace != range.uspace:
            raise ValueError('domain.uspace ({}) does not match range.uspace '
                             '({})'.format(domain.uspace, range.uspace))

        super().__init__(domain=domain, range=range, linear=True)

    def _call(self, x, out=None):
        """Apply resampling operator.

        The vector ``x`` is resampled using the sampling and interpolation
        operators of the underlying spaces.

        Examples
        --------
        Create two spaces with different number of points and create resampling
        operator. Apply operator to vector.

        >>> import odl
        >>> X = odl.uniform_discr(0, 1, 3)
        >>> Y = odl.uniform_discr(0, 1, 6)
        >>> resampling = Resampling(X, Y)
        >>> print(resampling([0, 1, 0]))
        [0.0, 0.0, 1.0, 1.0, 0.0, 0.0]

        The result depends on the interpolation chosen for the underlying
        spaces.

        >>> Z = odl.uniform_discr(0, 1, 3, interp='linear')
        >>> linear_resampling = Resampling(Z, Y)
        >>> print(linear_resampling([0, 1, 0]))
        [0.0, 0.25, 0.75, 0.75, 0.25, 0.0]
        """
        if out is None:
            return x.interpolation
        else:
            out.sampling(x.interpolation)

    @property
    def inverse(self):
        """Return an (approximate) inverse.

        Returns
        -------
        inverse : Resampling
            The resampling operator defined in the inverse direction.

        See Also
        --------
        adjoint : resampling is unitary, so adjoint is inverse.
        """
        return Resampling(self.range, self.domain)

    @property
    def adjoint(self):
        """Return an (approximate) adjoint.

        The result is only exact if the interpolation and sampling operators
        of the underlying spaces match exactly.

        Returns
        -------
        adjoint : Resampling
            The resampling operator defined in the inverse direction.

        Examples
        --------
        Create resampling operator and inverse

        >>> import odl
        >>> X = odl.uniform_discr(0, 1, 3)
        >>> Y = odl.uniform_discr(0, 1, 6)
        >>> resampling = Resampling(X, Y)
        >>> resampling_inv = resampling.inverse

        The inverse is proper left inverse if the resampling goes from a
        lower sampling to a higher sampling

        >>> x = [0.0, 1.0, 0.0]
        >>> print(resampling_inv(resampling(x)))
        [0.0, 1.0, 0.0]

        But can fail in the other direction

        >>> y = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0]
        >>> print(resampling(resampling_inv(y)))
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        """
        return self.inverse


_SUPPORTED_IMPL = ('numpy_ft', 'numpy_dft', 'pyfftw_ft', 'pyfftw_dft')
_SUPPORTED_KER_MODES = ('real', 'ft', 'dft', 'ft_hc', 'dft_hc')


class Convolution(Operator):

    """Discretized convolution operator.

    The continuous convolution of two functions ``f`` and ``g`` on R is
    defined as

        ``Conv(f, g)(x) = integrate_R ( f(x - y) * g(y) dy )``

    With the help of the Fourier transform, this operator can be written
    as a multiplication

        ``FT[Conv(f, g)] = sqrt(2 pi) FT(f) * FT(g)``

    This operator implements the case of one fixed argument, say ``g``.
    In this case, the convolution is a linear operator from ``L^p(R)``
    to itself (provided ``g in L^1(R)``), according to
    `Young's inequality for convolutions
    <https://en.wikipedia.org/wiki/Young's_inequality#\
Young.27s_inequality_for_convolutions>`_.
    """

    def __init__(self, dom, ran=None, kernel=None, **kwargs):
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
            'scipy_convolve', 'scipy_fftconvolve'``

            `element-like` for the range of `FourierTransform` defined
            on ``dom`` : The object is interpreted as the Fourier
            transform of a real-space kernel (mode ``ft`` or ``'ft_hc'``).
            The correct space can be calculated with `reciprocal_space`.
            Valid for ``impl``: ``'numpy_ft', 'pyfftw_ft'``

            `array-like`, arbitrary length : The object is interpreted as
            real-space kernel (mode ``'real'``) and can be shorter than
            the convolved function.
            Valid for ``impl``: ``'scipy_convolve'``

        kernel_mode : {'real', 'ft', 'ft_hc'}, optional
            How the provided kernel is to be interpreted. If not
            provided, the kernel is tried to convert into an element
            of ``dom`` or the Fourier transform range, in this order.

            'real' : element of ``dom`` (default)

            'ft' : function in the range of the Fourier transform

            'ft_hc' : function in the range of the half-complex
            (real-to-complex) Fourier transform

        impl : `str`, optional
            Implementation of the convolution. Available options are:

            'default_ft' : Fourier transform using NumPy/SciPy FFT
            (default)

            'pyfftw_ft' : Fourier transform using pyFFTW

            'scipy_convolve': Real-space convolution using
            `scipy.signal.convolve` (fast for short kernels)

            'scipy_fftconvolve': Fourier-space convolution using
            `scipy.signal.fftconvolve`

        axes : sequence of `int`, optional
            Dimensions in which to convolve. Default: all axes

        cache_ker_ft : `bool`, optional
            If `True`, the Fourier transform of the kernel is stored
            during the first evaluation.
            Default: `False`

        See also
        --------
        FourierTransform : discretization of the continuous FT
        DiscreteFourierTransform : "pure", trigonometric sum DFT
        """
        if not isinstance(dom, DiscreteLp):
            raise TypeError('domain {!r} is not a DiscreteLp instance.'
                            ''.format(dom))

        if ran is not None:
            raise NotImplementedError('custom range not implemented')
        else:
            ran = dom

        super().__init__(dom, ran, linear=True)

        # TODO: factor out code checking for valid combination of kernel
        # mode, impl and kernel
        # TODO: handle scipy.[fft]convolve impl
        impl = kwargs.pop('impl', 'numpy_ft')
        impl, impl_in = str(impl).lower(), impl
        if impl not in _SUPPORTED_IMPL:
            raise ValueError("implementation '{}' not understood."
                             ''.format(impl_in))
        self._impl = impl

        ker_mode = kwargs.pop('kernel_mode', 'real')
        ker_mode, ker_mode_in = str(ker_mode).lower(), ker_mode
        if ker_mode not in _SUPPORTED_KER_MODES:
            raise ValueError("kernel mode '{}' not understood."
                             ''.format(ker_mode_in))

        self._kernel_mode = ker_mode

        use_ft = (impl in ('numpy_ft', 'pyfftw_ft'))

        if not use_ft and ker_mode != 'real':
            raise ValueError("kernel mode 'real' is required for non-FT "
                             "based convolutions.")

        axes = kwargs.pop('axes', list(range(self.domain.ndim)))
        if ker_mode == 'real':
            halfcomplex = True  # use default depending on domain
        else:
            halfcomplex = ker_mode.endswith('hc')

        fft_impl = self.impl.split('_')[0]

        if use_ft:
            self._transform = FourierTransform(
                self.domain, axes=axes, halfcomplex=halfcomplex,
                impl=fft_impl)
            self._factor = np.sqrt(2 * np.pi) ** self.domain.ndim
        else:
            self._transform = None
            self._factor = None

        if ker_mode == 'real':
            self._kernel = self.domain.element(kernel)
            self._kernel_transform = None
        else:
            self._kernel = None
            self._kernel_transform = self.transform.range.element(kernel)

        self._cache_ker_ft = bool(kwargs.pop('cache_ker_ft', False))

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
        if not self.use_transform:
            # TODO: store if no transform used
            return None
        else:
            return self.transform.axes

    @property
    def use_transform(self):
        """Return `True` if an FT or DFT is used, otherwise `False`."""
        return self.transform is not None

    @property
    def kernel(self):
        """Real-space kernel of this transform if used, else `None`."""
        return self._kernel

    @property
    def kernel_transform(self):
        """Fourier-space kernel of this transform.

        It is either given as a parameter in the initialization or
        calculated during the first evaluation if caching was enabled.
        Otherwise, `None` is returned.
        """
        return self._kernel_transform

    def _call(self, x, out, **kwargs):
        """Implement ``self(x, out[, **kwargs])``.

        Keyword arguments are passed on to the transform.
        """
        # TODO: Calculate transform during init?
        if not self.use_transform:
            raise NotImplementedError('only transform-based convolution '
                                      'implemented.')

        if self.domain.field == ComplexNumbers():
            # Use out as a temporary
            tmp = self.transform.range.element(out.asarray())
        else:
            tmp = None

        x_trafo = self.transform(x, out=tmp, **kwargs)
        if self.kernel_transform is None:
            self._kernel_transform = self._ker_trafo()

        x_trafo *= self.kernel_transform
        if self._factor != 1.0:
            x_trafo *= self._factor

        self.transform.inverse(x_trafo, out=out, **kwargs)

    def _ker_trafo(self, **kwargs):
        """Helper for the calculation of the kernel transform."""
        if self.kernel is None:
            raise RuntimeError('invalid state: both kernel and '
                               'kernel_transform are None.')

        return self.transform(self.kernel, **kwargs)

    @property
    def adjoint(self):
        """Adjoint operator."""
        # TODO: this can be expensive. Cache this operator?
        if self.kernel_transform is None:
            self._kernel_transform = self._ker_trafo()

        # TODO: add conj to DiscreteLpVector
        adj_kernel_ft = self.transform.range.element(
            self.kernel_transform.asarray().conj())

        if self.transform.halfcomplex:
            kernel_mode = 'ft_hc'
        else:
            kernel_mode = 'ft'
        return Convolution(dom=self.domain,
                           kernel=adj_kernel_ft, kernel_mode=kernel_mode,
                           impl=self.impl, axes=self.axes)


if __name__ == '__main__':
    # pylint: disable=wrong-import-position
    from odl.util.testutils import run_doctests
    run_doctests()
