"""
Module for defining bases in the Fourier family
"""
import numpy as np
import pyfftw
from shenfun.spectralbase import SpectralBase
from shenfun.utilities import inheritdocstrings
from shenfun.optimization import convolve

__all__ = ['FourierBase', 'R2CBasis', 'C2CBasis']

#pylint: disable=method-hidden, no-member, line-too-long, arguments-differ

@inheritdocstrings
class FourierBase(SpectralBase):
    r"""Fourier base class

    A basis function :math:`\phi_k` is given as

    .. math::

        \phi_k(x) = \exp(ikx)

    and an expansion is given as

    .. math::
       :label: u

        u(x) = \sum_k \hat{u}_k \exp(ikx)

    where

    .. math::

        k = -N/2, -N/2+1, ..., N/2-1

    However, since :math:`\exp(ikx) = \exp(i(k \pm N)x)` this expansion can
    also be written as an interpolator

    .. math::
       :label: u2

        u(x) = \sum_k \frac{\hat{u}_k}{c_k} \exp(ikx)

    where

    .. math::

        k = -N/2, -N/2+1, ..., N/2-1, N/2

    and :math:`c_{N/2} = c_{-N/2} = 2`, whereas :math:`c_k = 1` for
    :math:`k=-N/2+1, ..., N/2-1`. Furthermore,
    :math:`\hat{u}_{N/2} = \hat{u}_{-N/2}`.

    The interpolator form is used for computing odd derivatives. Otherwise,
    it makes no difference and therefore :eq:`u` is used in transforms, since
    this is the form expected by pyfftw.

    The inner product is defined as

    .. math::

        (u, v) = \frac{1}{L} \int_{0}^{L} u \overline{v} dx

    where :math:`\overline{v}` is the complex conjugate of :math:`v`, and
    :math:`L` is the length of the (periodic) domain.

    Parameters
    ----------
        N : int
            Number of quadrature points. Should be even for efficiency, but
            this is not required.
        padding_factor : float, optional
                         Factor for padding backward transforms.
                         padding_factor=1.5 corresponds to a 3/2-rule for
                         dealiasing.
        domain : 2-tuple of floats, optional
                 The computational domain.
        dealias_direct : bool, optional
                         True for dealiasing using 2/3-rule. Must be used with
                         padding_factor == 1.
    """

    def __init__(self, N, padding_factor=1., domain=(0, 2*np.pi),
                 dealias_direct=False):
        self.dealias_direct = dealias_direct
        SpectralBase.__init__(self, N, '', padding_factor, domain)

    @staticmethod
    def family():
        return 'fourier'

    def points_and_weights(self, N, scaled=False):
        points = np.arange(N, dtype=np.float)*2*np.pi/N
        if scaled is True:
            points = self.map_true_domain(points)
        return points, np.array([2*np.pi/N])

    def vandermonde(self, x):
        """Return Vandermonde matrix

        Parameters
        ----------
            x : array
                points for evaluation

        """
        k = self.wavenumbers(self.N, 0)
        x = np.atleast_1d(x)
        return np.exp(1j*x[:, np.newaxis]*k[np.newaxis, :])

    def get_vandermonde_basis_derivative(self, V, k=0):
        """Return k'th derivative of basis as a Vandermonde matrix

        Parameters
        ----------
            V : array of ndim = 2
                Chebyshev Vandermonde matrix
            k : int
                k'th derivative
        """
        if k > 0:
            l = self.wavenumbers(self.N, 0, scaled=True)
            V = V*((1j*l)**k)[np.newaxis, :]
        return V

    # Reimplemented for efficiency (smaller array in *= when truncated)
    def forward(self, input_array=None, output_array=None, fast_transform=True):
        if fast_transform is False:
            return SpectralBase.forward(self, input_array, output_array, False)

        if input_array is not None:
            self.forward.input_array[...] = input_array

        self.forward.xfftn()
        self._truncation_forward(self.forward.tmp_array,
                                 self.forward.output_array)
        self.forward._output_array *= (1./self.N/self.padding_factor)

        if output_array is not None:
            output_array[...] = self.forward.output_array
            return output_array
        return self.forward.output_array

    def apply_inverse_mass(self, array):
        """Apply inverse mass

        Note
        ----
        Mass matrix is identity, so do nothing

        Parameters
        ----------
            array : array (input/output)
                    Expansion coefficients.
        """
        return array

    def evaluate_expansion_all(self, input_array, output_array, fast_transform=True):
        if fast_transform is False:
            SpectralBase.evaluate_expansion_all(self, input_array, output_array, False)
        else:
            self.backward.xfftn(normalise_idft=False)

    def evaluate_scalar_product(self, input_array, output_array, fast_transform=True):
        if fast_transform is False:
            self.vandermonde_scalar_product(input_array, output_array)
            return
        output = self.scalar_product.xfftn()
        output *= (1./self.N/self.padding_factor)

    def vandermonde_scalar_product(self, input_array, output_array):
        SpectralBase.vandermonde_scalar_product(self, input_array, output_array)
        output_array *= 0.5/np.pi

    def reference_domain(self):
        return (0., 2*np.pi)


class R2CBasis(FourierBase):
    """Fourier basis class for real to complex transforms
    """

    def __init__(self, N, padding_factor=1., plan=False, domain=(0., 2.*np.pi),
                 dealias_direct=False):
        FourierBase.__init__(self, N, padding_factor, domain, dealias_direct)
        self.N = N
        self._xfftn_fwd = pyfftw.builders.rfft
        self._xfftn_bck = pyfftw.builders.irfft
        if plan:
            self.plan((int(np.floor(padding_factor*N)),), 0, np.float, {})

    def wavenumbers(self, N, axis=0, scaled=False, eliminate_highest_freq=False):
        N = list(N) if np.ndim(N) else [N]
        assert self.N == N[axis]
        k = np.fft.rfftfreq(N[axis], 1./N[axis])
        if N[axis] % 2 == 0 and eliminate_highest_freq:
            k[-1] = 0
        if scaled:
            k *= self.domain_factor()
        K = self.broadcast_to_ndims(k, len(N), axis)
        return K

    def _get_truncarray(self, shape, dtype):
        shape = list(shape)
        shape[self.axis] = int(shape[self.axis] / self.padding_factor)
        shape[self.axis] = shape[self.axis]//2 + 1
        return pyfftw.empty_aligned(shape, dtype=dtype)

    #def eval(self, x, fk):
    #    x = self.map_reference_domain(x)
    #    V = self.vandermonde(x)
    #    return np.dot(V, fk) + np.conj(np.dot(V[:, 1:-1], fk[1:-1]))

    def slice(self):
        return slice(0, self.N//2+1)

    def vandermonde_evaluate_expansion_all(self, input_array, output_array):
        assert abs(self.padding_factor-1) < 1e-8
        assert self.N == output_array.shape[self.axis]
        points = self.points_and_weights(self.N)[0]
        P = self.vandermonde(points)
        if output_array.ndim == 1:
            output_array[:] = np.dot(P, input_array).real
            if self.N % 2 == 0:
                output_array += np.conj(np.dot(P[:, 1:-1], input_array[1:-1])).real
            else:
                output_array += np.conj(np.dot(P[:, 1:], input_array[1:])).real

        else:
            fc = np.moveaxis(input_array, self.axis, -2)
            array = np.dot(P, fc).real
            s = [slice(None)]*fc.ndim
            if self.N % 2 == 0:
                s[-2] = slice(1, -1)
                array += np.conj(np.dot(P[:, 1:-1], fc[s])).real
            else:
                s[-2] = slice(1, None)
                array += np.conj(np.dot(P[:, 1:], fc[s])).real

            output_array[:] = np.moveaxis(array, 0, self.axis)

    def vandermonde_evaluate_expansion(self, points, input_array, output_array):
        """Evaluate expansion at certain points, possibly different from
        the quadrature points

        This method assumes the array is locally available in full, i.e., the
        multidimensional arrays are aligned along the axis of this basis.

        Parameters
        ----------
            P : 2D array
                Vandermode matrix containing local points only
            input_array : array
                          Expansion coefficients
            output_array : array
                           Function values on points
            last_conj_index : int
                              The last index to sum over for conj part
                              (R2CBasis only)
            offset : int
                     Global offset (MPI)

        Note
        ----
        This method is complicated by the fact that the data may not be aligned
        along the axis of this basis.

        """
        assert abs(self.padding_factor-1) < 1e-8
        points = self.map_reference_domain(points)
        P = self.vandermonde(points)
        assert output_array.ndim == 1 # Multidimensional should use vandermonde_evaluate_local_expansion
        output_array[:] = np.dot(P, input_array).real
        if self.N % 2 == 0:
            output_array += np.conj(np.dot(P[:, 1:-1], input_array[1:-1])).real
        else:
            output_array += np.conj(np.dot(P[:, 1:], input_array[1:])).real

        return output_array

    def vandermonde_evaluate_local_expansion(self, P, input_array, output_array,
                                             last_conj_index, offset):
        """Evaluate expansion at certain points, possibly different from
        the quadrature points

        This method does not assume that the multidimensional arrays are aligned
        along the axis of this basis.

        Parameters
        ----------
            P : 2D array
                Vandermode matrix containing local points only
            input_array : array
                          Expansion coefficients
            output_array : array
                           Function values on points
            last_conj_index : int
                              The last index to sum over for conj part
                              (R2CBasis only)
            offset : int
                     Global offset (MPI)

        Note
        ----
        This method is complicated by the fact that the data may not be aligned
        in the direction of this base's axis

        """
        fc = np.moveaxis(input_array, self.axis, -2)
        array = np.dot(P, fc)
        s = [slice(None)]*fc.ndim
        N = P.shape[1]
        if offset == 0:
            s[-2] = slice(1, N)
            if N > last_conj_index:
                s[-2] = slice(1, N-1)
        else:
            s[-2] = slice(0, N)
            if N > last_conj_index:
                s[-2] = slice(0, N-1)
        sl = [slice(None)]*2
        sl[-1] = s[-2]
        array += np.conj(np.dot(P[sl], fc[s]))
        output_array[:] = np.moveaxis(array, 0, self.axis)
        return output_array

    def _truncation_forward(self, padded_array, trunc_array):
        if self.padding_factor > 1.0+1e-8:
            trunc_array.fill(0)
            N = trunc_array.shape[self.axis]
            s = [slice(None)]*trunc_array.ndim
            s[self.axis] = slice(0, N)
            trunc_array[:] = padded_array[s]
            if self.N % 2 == 0:
                s[self.axis] = N-1
                trunc_array[s] = trunc_array[s].real
                trunc_array[s] *= 2

    def _padding_backward(self, trunc_array, padded_array):
        if self.padding_factor > 1.0+1e-8:
            padded_array.fill(0)
            N = trunc_array.shape[self.axis]
            s = [slice(0, n) for n in trunc_array.shape]
            padded_array[s] = trunc_array[s]
            if self.N % 2 == 0:  # Symmetric Fourier interpolator
                s[self.axis] = N-1
                padded_array[s] = padded_array[s].real
                padded_array[s] *= 0.5

        elif self.dealias_direct:
            N = self.N
            su = [slice(None)]*padded_array.ndim
            su[self.axis] = slice(int(np.floor(N/3.)), None)
            padded_array[su] = 0

    def convolve(self, u, v, uv=None, fast=True):
        """Convolution of u and v.

        Parameters
        ----------
            u : array
            v : array
            uv : array, optional
            fast : bool, optional
                   Whether to use fast transforms in computing convolution

        Note
        ----
        Note that this method is only valid for 1D data, and that
        for multidimensional arrays one should use corresponding method
        in the TensorProductSpace class.

        """
        N = self.N

        if fast is True:
            if uv is None:
                uv = self.forward.output_array.copy()

            assert self.padding_factor > 1.0, "padding factor must be > 3/2+1/N to perform convolution without aliasing"
            u2 = self.backward.output_array.copy()
            u3 = self.backward.output_array.copy()
            u2 = self.backward(u, u2)
            u3 = self.backward(v, u3)
            uv = self.forward(u2*u3, uv)

        else:
            if uv is None:
                uv = np.zeros(N+1, dtype=u.dtype)
            Np = N if not N % 2 == 0 else N+1
            k1 = np.fft.fftfreq(Np, 1./Np).astype(int)
            convolve.convolve_real_1D(u, v, uv, k1)

            #u1 = np.hstack((u, np.conj(u[1:][::-1])))
            #if N % 2 == 0:
                #u1[N//2:N//2+2] *= 0.5
            #v1 = np.hstack((v, np.conj(v[1:][::-1])))
            #if N % 2 == 0:
                #v1[N//2:N//2+2] *= 0.5

            #for m in range(N):
                #vc = np.roll(v1, -(m+1))
                #s = u1*vc[::-1]
                #ki = k1 + np.roll(k1, -(m+1))[::-1]
                #z0 = np.argwhere(ki == m)
                #z1 = np.argwhere(ki == m-N)
                #uv[m] = np.sum(s[z0])
                #uv[m-N] = np.sum(s[z1])

            #for m in k1:
                #for n in k1:
                    #p = m + n
                    #if p >= 0:
                        #if N % 2 == 0:
                            #if abs(m) == N//2:
                                #um = u[abs(m)]*0.5
                            #elif m >= 0:
                                #um = u[m]
                            #else:
                                #um = np.conj(u[abs(m)])
                            #if abs(n) == N//2:
                                #vn = v[abs(n)]*0.5
                            #elif n >= 0:
                                #vn = v[n]
                            #else:
                                #vn = np.conj(v[abs(n)])
                        #else:
                            #if m >= 0:
                                #um = u[m]
                            #elif m < 0:
                                #um = np.conj(u[abs(m)])
                            #if n >= 0:
                                #vn = v[n]
                            #elif n < 0:
                                #vn = np.conj(v[abs(n)])
                        #uv[p] += um*vn
        return uv


class C2CBasis(FourierBase):
    """Fourier basis class for complex to complex transforms
    """

    def __init__(self, N, padding_factor=1., plan=False, domain=(0., 2.*np.pi),
                 dealias_direct=False):
        FourierBase.__init__(self, N, padding_factor, domain, dealias_direct)
        self.N = N
        self._xfftn_fwd = pyfftw.builders.fft
        self._xfftn_bck = pyfftw.builders.ifft
        if plan:
            self.plan((int(np.floor(padding_factor*N)),), 0, np.complex, {})

    def wavenumbers(self, N, axis=0, scaled=False, eliminate_highest_freq=False):
        N = list(N) if np.ndim(N) else [N]
        assert self.N == N[axis]
        k = np.fft.fftfreq(N[axis], 1./N[axis])
        if N[axis] % 2 == 0 and eliminate_highest_freq:
            k[N[axis]//2] = 0
        if scaled:
            k *= self.domain_factor()
        K = self.broadcast_to_ndims(k, len(N), axis)
        return K

    def slice(self):
        return slice(0, self.N)

    def _truncation_forward(self, padded_array, trunc_array):
        if self.padding_factor > 1.0+1e-8:
            trunc_array.fill(0)
            N = trunc_array.shape[self.axis]
            su = [slice(None)]*trunc_array.ndim
            su[self.axis] = slice(0, N//2+1)
            trunc_array[su] = padded_array[su]
            su[self.axis] = slice(-(N//2), None)
            trunc_array[su] += padded_array[su]

    def _padding_backward(self, trunc_array, padded_array):
        if self.padding_factor > 1.0+1e-8:
            padded_array.fill(0)
            N = trunc_array.shape[self.axis]
            su = [slice(None)]*trunc_array.ndim
            su[self.axis] = slice(0, N//2+1)
            padded_array[su] = trunc_array[su]
            su[self.axis] = slice(-(N//2), None)
            padded_array[su] = trunc_array[su]
            if self.N % 2 == 0:  # Use symmetric Fourier interpolator
                su[self.axis] = N//2
                padded_array[su] *= 0.5
                su[self.axis] = -(N//2)
                padded_array[su] *= 0.5

        elif self.dealias_direct:
            N = trunc_array.shape[self.axis]
            su = [slice(None)]*padded_array.ndim
            su[self.axis] = slice(int(np.floor(N/3.)), int(np.floor(2./3.*N)))
            padded_array[su] = 0

    def convolve(self, u, v, uv=None, fast=True):
        """Convolution of u and v.

        Parameters
        ----------
            u : array
            v : array
            uv : array, optional
            fast : bool, optional
                   Whether to use fast transforms in computing convolution

        Note
        ----
        Note that this method is only valid for 1D data, and that
        for multidimensional arrays one should use corresponding method
        in the TensorProductSpace class.

        """
        assert len(u.shape) == 1
        N = self.N

        if fast:
            if uv is None:
                uv = self.forward.output_array.copy()

            assert self.padding_factor > 1.0, "padding factor must be > 3/2+1/N to perform convolution without aliasing"
            u2 = self.backward.output_array.copy()
            u3 = self.backward.output_array.copy()
            u2 = self.backward(u, u2)
            u3 = self.backward(v, u3)
            uv = self.forward(u2*u3, uv)

        else:

            if uv is None:
                uv = np.zeros(2*N, dtype=u.dtype)

            Np = N if not N % 2 == 0 else N+1
            k = np.fft.fftfreq(Np, 1./Np).astype(int)
            convolve.convolve_1D(u, v, uv, k)

            #if N % 2 == 0:
                #u = np.hstack((u[:N//2], u[N//2], u[N//2:]))
                #u[N//2:N//2+2] *= 0.5
                #v = np.hstack((v[:N//2], v[N//2], v[N//2:]))
                #v[N//2:N//2+2] *= 0.5

            #for m in range(Np):
                #vc = np.roll(v, -(m+1))
                #s = u*vc[::-1]
                #ki = k + np.roll(k, -(m+1))[::-1]
                #z0 = np.argwhere(ki == m)
                #z1 = np.argwhere(ki == m-Np)
                #uv[m] = np.sum(s[z0])
                #uv[m-Np] = np.sum(s[z1])

            #for m in k:
                #for n in k:
                    #p = m + n
                    #if N % 2 == 0:
                        #if abs(m) == N//2:
                            #um = u[m]*0.5
                        #else:
                            #um = u[m]
                        #if abs(n) == N//2:
                            #vn = v[n]*0.5
                        #else:
                            #vn = v[n]
                    #else:
                        #um = u[m]
                        #vn = v[n]
                    #uv[p] += um*vn

        return uv

