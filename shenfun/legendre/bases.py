"""
Module for defining bases in the Legendre family
"""

import numpy as np
from numpy.polynomial import legendre as leg
import pyfftw
import functools
from shenfun.spectralbase import SpectralBase, work, Transform
from shenfun.utilities import inheritdocstrings
from .lobatto import legendre_lobatto_nodes_and_weights

__all__ = ['LegendreBase', 'Basis', 'ShenDirichletBasis',
           'ShenBiharmonicBasis', 'ShenNeumannBasis',
           'SecondNeumannBasis']

#pylint: disable=method-hidden,no-else-return,not-callable,abstract-method,no-member,cyclic-import


@inheritdocstrings
class LegendreBase(SpectralBase):
    """Base class for all Legendre bases

    Parameters
    ----------
        N : int, optional
            Number of quadrature points
        quad : str, optional
               Type of quadrature

               - LG - Legendre-Gauss
               - GL - Legendre-Gauss-Lobatto

        domain : 2-tuple of floats, optional
                 The computational domain
    """

    def __init__(self, N=0, quad="LG", domain=(-1., 1.)):
        SpectralBase.__init__(self, N, quad, domain=domain)
        self.forward = functools.partial(self.forward, fast_transform=False)
        self.backward = functools.partial(self.backward, fast_transform=False)
        self.scalar_product = functools.partial(self.scalar_product, fast_transform=False)

    @staticmethod
    def family():
        return 'legendre'

    def reference_domain(self):
        return (-1., 1.)

    def points_and_weights(self, N, scaled=False):
        if self.quad == "LG":
            points, weights = leg.leggauss(N)
        elif self.quad == "GL":
            points, weights = legendre_lobatto_nodes_and_weights(N)
        else:
            raise NotImplementedError

        if scaled is True:
            points = self.map_true_domain(points)

        return points, weights

    def vandermonde(self, x):
        """Return Legendre Vandermonde matrix

        Parameters
        ----------
            x : array
                points for evaluation

        """
        V = leg.legvander(x, self.N-1)
        return V

    def get_vandermonde_basis_derivative(self, V, k=0):
        """Return k'th derivatives of basis as a Vandermonde matrix

        Parameters
        ----------
            V : array of ndim = 2
                Chebyshev Vandermonde matrix
            k : int
                k'th derivative
        """
        assert self.N == V.shape[1]
        if k > 0:
            D = np.zeros((self.N, self.N))
            D[:-k, :] = leg.legder(np.eye(self.N), k)
            V = np.dot(V, D)

        return self.get_vandermonde_basis(V)

    def plan(self, shape, axis, dtype, options):
        if isinstance(axis, tuple):
            axis = axis[0]

        if isinstance(self.forward, Transform):
            if self.forward.input_array.shape == shape and self.axis == axis:
                # Already planned
                return

        if isinstance(axis, tuple):
            axis = axis[0]

        U = pyfftw.empty_aligned(shape, dtype=dtype)
        V = pyfftw.empty_aligned(shape, dtype=dtype)
        U.fill(0)
        V.fill(0)

        self.axis = axis
        self.forward = Transform(self.forward, None, U, V, V)
        self.backward = Transform(self.backward, None, V, V, U)
        self.scalar_product = Transform(self.scalar_product, None, U, V, V)


@inheritdocstrings
class Basis(LegendreBase):
    """Basis for regular Legendre series

    Parameters
    ----------
        N : int, optional
            Number of quadrature points
        quad : str, optional
               Type of quadrature

               - LG - Legendre-Gauss
               - GL - Legendre-Gauss-Lobatto

        plan : bool, optional
               Plan transforms on __init__ or not. If basis is part of a
               TensorProductSpace, then planning needs to be delayed.
        domain : 2-tuple of floats, optional
                 The computational domain
    """

    def __init__(self, N=0, quad="GL", plan=False, domain=(-1., 1.)):
        LegendreBase.__init__(self, N, quad, domain=domain)
        if plan:
            self.plan(N, 0, np.float, {})

    def eval(self, x, fk, output_array=None):
        if output_array is None:
            output_array = np.zeros(x.shape)
        x = self.map_reference_domain(x)
        output_array[:] = leg.legval(x, fk)
        return output_array


@inheritdocstrings
class ShenDirichletBasis(LegendreBase):
    """Shen Legendre basis for Dirichlet boundary conditions

    Parameters
    ----------
        N : int, optional
            Number of quadrature points
        quad : str, optional
               Type of quadrature

               - LG - Legendre-Gauss
               - GL - Legendre-Gauss-Lobatto

        bc : tuple of numbers
             Boundary conditions at edges of domain
        plan : bool, optional
               Plan transforms on __init__ or not. If basis is part of a
               TensorProductSpace, then planning needs to be delayed.
        domain : 2-tuple of floats, optional
                 The computational domain
        scaled : bool, optional
                 Whether or not to scale test functions with 1/sqrt(4k+6).
                 Scaled test functions give a stiffness matrix equal to the
                 identity matrix.
    """
    def __init__(self, N=0, quad="LG", bc=(0., 0.), plan=False,
                 domain=(-1., 1.), scaled=False):
        LegendreBase.__init__(self, N, quad, domain=domain)
        from shenfun.tensorproductspace import BoundaryValues
        self.LT = Basis(N, quad)
        self._scaled = scaled
        self._factor = np.ones(1)
        if plan:
            self.plan(N, 0, np.float, {})
        self.bc = BoundaryValues(self, bc=bc)

    def set_factor_array(self, v):
        if self.is_scaled():
            if not self._factor.shape == v.shape:
                k = self.wavenumbers(v.shape, self.axis).astype(np.float)
                self._factor = 1./np.sqrt(4*k+6)

    def is_scaled(self):
        return self._scaled

    def get_vandermonde_basis(self, V):
        P = np.zeros(V.shape)
        if not self.is_scaled():
            P[:, :-2] = V[:, :-2] - V[:, 2:]
        else:
            k = np.arange(self.N-2).astype(np.float)
            P[:, :-2] = (V[:, :-2] - V[:, 2:])/np.sqrt(4*k+6)
        P[:, -2] = (V[:, 0] + V[:, 1])/2
        P[:, -1] = (V[:, 0] - V[:, 1])/2
        return P

    #def evaluate_expansion_all(self, input_array, output_array,
    #                           fast_transform=False): # pragma: no cover
    #    # Not used since there are no fast transforms for Legendre
    #    w_hat = work[(input_array, 0)]
    #    s0 = self.sl(slice(0, -2))
    #    s1 = self.sl(slice(2, None))
    #    self.set_factor_array(input_array)
    #    w_hat[s0] = input_array[s0]*self._factor
    #    w_hat[s1] -= input_array[s0]*self._factor
    #    self.bc.apply_before(w_hat, False, (0.5, 0.5))
    #    output_array = self.LT.backward(w_hat)
    #    assert input_array is self.backward.input_array
    #    assert output_array is self.backward.output_array

    def slice(self):
        return slice(0, self.N-2)

    def spectral_shape(self):
        return self.N-2

    def eval(self, x, fk, output_array=None):
        if output_array is None:
            output_array = np.zeros(x.shape)
        x = self.map_reference_domain(x)
        w_hat = work[(fk, 0)]
        self.set_factor_array(fk)
        output_array[:] = leg.legval(x, fk[:-2]*self._factor)
        w_hat[2:] = fk[:-2]*self._factor
        output_array -= leg.legval(x, w_hat)
        output_array += 0.5*(fk[-1]*(1+x)+fk[-2]*(1-x))
        return output_array

    def plan(self, shape, axis, dtype, options):
        if isinstance(axis, tuple):
            axis = axis[0]

        if isinstance(self.forward, Transform):
            if self.forward.input_array.shape == shape and self.axis == axis:
                # Already planned
                return

        self.LT.plan(shape, axis, dtype, options)
        self.axis = self.LT.axis
        U, V = self.LT.forward.input_array, self.LT.forward.output_array
        self.forward = Transform(self.forward, None, U, V, V)
        self.backward = Transform(self.backward, None, V, V, U)
        self.scalar_product = Transform(self.scalar_product, None, U, V, V)


@inheritdocstrings
class ShenNeumannBasis(LegendreBase):
    """Shen basis for homogeneous Neumann boundary conditions

    Parameters
    ----------
        N : int, optional
            Number of quadrature points
        quad : str, optional
               Type of quadrature

               - LG - Legendre-Gauss
               - GL - Legendre-Gauss-Lobatto

        mean : number
               mean value
        plan : bool, optional
               Plan transforms on __init__ or not. If basis is part of a
               TensorProductSpace, then planning needs to be delayed.
        domain : 2-tuple of floats, optional
                 The computational domain
    """

    def __init__(self, N=0, quad="LG", mean=0, plan=False, domain=(-1., 1.)):
        LegendreBase.__init__(self, N, quad, domain=domain)
        self.mean = mean
        self.LT = Basis(N, quad)
        self._factor = np.zeros(0)
        if plan:
            self.plan(N, 0, np.float, {})

    def get_vandermonde_basis(self, V):
        assert self.N == V.shape[1]
        P = np.zeros(V.shape)
        k = np.arange(self.N).astype(np.float)
        P[:, :-2] = V[:, :-2] - (k[:-2]*(k[:-2]+1)/(k[:-2]+2))/(k[:-2]+3)*V[:, 2:]
        return P

    def set_factor_array(self, v):
        if not self._factor.shape == v.shape:
            k = self.wavenumbers(v.shape, self.axis).astype(np.float)
            self._factor = k*(k+1)/(k+2)/(k+3)

    def scalar_product(self, input_array=None, output_array=None, fast_transform=False):
        output = SpectralBase.scalar_product(self, input_array, output_array, False)

        s = self.sl(0)
        output[s] = self.mean*np.pi
        s[self.axis] = slice(-2, None)
        output[s] = 0
        return output

    #def evaluate_expansion_all(self, input_array, output_array): # pragma: no cover
    #    # Not used since there are no fast transforms for Legendre
    #    w_hat = work[(input_array, 0)]
    #    self.set_factor_array(input_array)
    #    s0 = self.sl(slice(0, -2))
    #    s1 = self.sl(slice(2, None))
    #    w_hat[s0] = input_array[s0]
    #    w_hat[s1] -= self._factor*input_array[s0]
    #    output_array = self.LT.backward(w_hat)

    def slice(self):
        return slice(0, self.N-2)

    def spectral_shape(self):
        return self.N-2

    def eval(self, x, fk, output_array=None):
        if output_array is None:
            output_array = np.zeros(x.shape)
        x = self.map_reference_domain(x)
        w_hat = work[(fk, 0)]
        self.set_factor_array(fk)
        output_array[:] = leg.legval(x, fk[:-2])
        w_hat[2:] = self._factor*fk[:-2]
        output_array -= leg.legval(x, w_hat)
        return output_array

    def plan(self, shape, axis, dtype, options):
        if isinstance(axis, tuple):
            axis = axis[0]

        if isinstance(self.forward, Transform):
            if self.forward.input_array.shape == shape and self.axis == axis:
                # Already planned
                return

        self.LT.plan(shape, axis, dtype, options)
        self.axis = self.LT.axis
        U, V = self.LT.forward.input_array, self.LT.forward.output_array
        self.forward = Transform(self.forward, None, U, V, V)
        self.backward = Transform(self.backward, None, V, V, U)
        self.scalar_product = Transform(self.scalar_product, None, U, V, V)


@inheritdocstrings
class ShenBiharmonicBasis(LegendreBase):
    """Shen biharmonic basis

    Homogeneous Dirichlet and Neumann boundary conditions.

    Parameters
    ----------
        N : int, optional
            Number of quadrature points
        quad : str, optional
               Type of quadrature

               - LG - Legendre-Gauss
               - GL - Legendre-Gauss-Lobatto

        plan : bool, optional
               Plan transforms on __init__ or not. If basis is part of a
               TensorProductSpace, then planning needs to be delayed.
        domain : 2-tuple of floats, optional
                 The computational domain
    """
    def __init__(self, N=0, quad="LG", plan=False, domain=(-1., 1.)):
        LegendreBase.__init__(self, N, quad, domain=domain)
        self.LT = Basis(N, quad)
        self._factor1 = np.zeros(0)
        self._factor2 = np.zeros(0)
        if plan:
            self.plan(N, 0, np.float, {})

    def get_vandermonde_basis(self, V):
        P = np.zeros_like(V)
        k = np.arange(V.shape[1]).astype(np.float)[:-4]
        P[:, :-4] = V[:, :-4] - (2*(2*k+5)/(2*k+7))*V[:, 2:-2] + ((2*k+3)/(2*k+7))*V[:, 4:]
        return P

    def set_factor_arrays(self, v):
        s = [slice(None)]*v.ndim
        s[self.axis] = self.slice()
        if not self._factor1.shape == v[s].shape:
            k = self.wavenumbers(v.shape, axis=self.axis).astype(np.float)
            self._factor1 = (-2*(2*k+5)/(2*k+7)).astype(float)
            self._factor2 = ((2*k+3)/(2*k+7)).astype(float)

    def scalar_product(self, input_array=None, output_array=None, fast_transform=False):
        output = LegendreBase.scalar_product(self, input_array, output_array, False)
        output[self.sl(slice(-4, None))] = 0
        return output

    #@optimizer
    def set_w_hat(self, w_hat, fk, f1, f2): # pragma: no cover
        s = self.sl(self.slice())
        s2 = self.sl(slice(2, -2))
        s4 = self.sl(slice(4, None))
        w_hat[s] = fk[s]
        w_hat[s2] += f1*fk[s]
        w_hat[s4] += f2*fk[s]
        return w_hat

    #def evaluate_expansion_all(self, input_array, output_array): # pragma: no cover
    #    # Not used since there are no fast transforms for Legendre
    #    w_hat = work[(input_array, 0)]
    #    self.set_factor_arrays(input_array)
    #    w_hat = self.set_w_hat(w_hat, input_array, self._factor1, self._factor2)
    #    output_array = self.LT.backward(w_hat)

    def slice(self):
        return slice(0, self.N-4)

    def spectral_shape(self):
        return self.N-4

    def eval(self, x, fk, output_array=None):
        if output_array is None:
            output_array = np.zeros(x.shape)
        x = self.map_reference_domain(x)
        w_hat = work[(fk, 0)]
        self.set_factor_arrays(fk)
        output_array[:] = leg.legval(x, fk[:-4])
        w_hat[2:-2] = self._factor1*fk[:-4]
        output_array += leg.legval(x, w_hat[:-2])
        w_hat[4:] = self._factor2*fk[:-4]
        w_hat[:4] = 0
        output_array += leg.legval(x, w_hat)
        return output_array

    def plan(self, shape, axis, dtype, options):
        if isinstance(axis, tuple):
            axis = axis[0]

        if isinstance(self.forward, Transform):
            if self.forward.input_array.shape == shape and self.axis == axis:
                # Already planned
                return

        self.LT.plan(shape, axis, dtype, options)
        self.axis = self.LT.axis
        U, V = self.LT.forward.input_array, self.LT.forward.output_array
        self.forward = Transform(self.forward, None, U, V, V)
        self.backward = Transform(self.backward, None, V, V, U)
        self.scalar_product = Transform(self.scalar_product, None, U, V, V)


## Experimental!
@inheritdocstrings
class SecondNeumannBasis(LegendreBase): # pragma: no cover
    """Shen basis for homogeneous second order Neumann boundary conditions

    Parameters
    ----------
        N : int, optional
            Number of quadrature points
        quad : str, optional
               Type of quadrature

               - LG - Legendre-Gauss
               - GL - Legendre-Gauss-Lobatto

        mean : number
               Mean value of solution
        plan : bool, optional
               Plan transforms on __init__ or not. If basis is part of a
               TensorProductSpace, then planning needs to be delayed.
        domain : 2-tuple of floats, optional
                 The computational domain
    """
    def __init__(self, N=0, quad="LG", mean=0, plan=False, domain=(-1., 1.)):
        LegendreBase.__init__(self, N, quad, domain=domain)
        self.mean = mean
        self.LT = Basis(N, quad)
        self._factor = np.zeros(0)
        if plan:
            self.plan(N, 0, np.float, {})

    def get_vandermonde_basis(self, V):
        assert self.N == V.shape[1]
        P = np.zeros(V.shape)
        k = np.arange(self.N).astype(np.float)[:-4]
        a_k = -(k+1)*(k+2)*(2*k+3)/((k+3)*(k+4)*(2*k+7))

        P[:, :-4] = V[:, :-4] + (a_k-1)*V[:, 2:-2] - a_k*V[:, 4:]
        P[:, -4] = V[:, 0]
        P[:, -3] = V[:, 1]
        return P

    def set_factor_array(self, v):
        if not self._factor.shape == v.shape:
            k = self.wavenumbers(v.shape, self.axis).astype(np.float)
            self._factor = -(k+1)*(k+2)*(2*k+3)/((k+3)*(k+4)*(2*k+7))

    #def evaluate_expansion_all(self, fk, output_array):
        #w_hat = work[(fk, 0)]
        #self.set_factor_array(fk)
        #s0 = self.sl(slice(0, -4))
        #s1 = self.sl(slice(2, -2))
        #s2 = self.sl(slice(4, None))
        #w_hat[s0] = fk[s0]
        #w_hat[s1] += (self._factor-1)*fk[s0]
        #w_hat[s2] -= self._factor*fk[s0]
        #output_array = self.LT.backward(w_hat)
        #return output_array

    def slice(self):
        return slice(0, self.N-2)

    def spectral_shape(self):
        return self.N-2

    #def eval(self, x, input_array):
        #w_hat = work[(input_array, 0)]
        #self.set_factor_array(input_array)
        #f = leg.legval(x, input_array[:-2])
        #w_hat[2:] = self._factor*input_array[:-2]
        #f -= leg.legval(x, w_hat)
        #return f

    def plan(self, shape, axis, dtype, options):
        if isinstance(axis, tuple):
            axis = axis[0]

        if isinstance(self.forward, Transform):
            if self.forward.input_array.shape == shape and self.axis == axis:
                # Already planned
                return

        self.LT.plan(shape, axis, dtype, options)
        self.axis = self.LT.axis
        U, V = self.LT.forward.input_array, self.LT.forward.output_array
        self.forward = Transform(self.forward, None, U, V, V)
        self.backward = Transform(self.backward, None, V, V, U)
        self.scalar_product = Transform(self.scalar_product, None, U, V, V)
