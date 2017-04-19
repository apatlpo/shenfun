r"""
Solve Poisson equation in 2D with periodic bcs in one direction
and homogeneous Dirichlet in the other

    \nabla^2 u = f,

Use Fourier basis for the periodic direction and Shen's Dirichlet basis for the
non-periodic direction.

The equation to solve for the Legendre basis is

     (\nabla u, \nabla v) = -(f, v)

whereas for Chebyshev we solve

     (\nabla^2 u, v) = (f, v)

"""
import sys
import importlib
from sympy import symbols, cos, sin, exp, lambdify
import numpy as np
import matplotlib.pyplot as plt
from shenfun.fourier.bases import R2CBasis, C2CBasis
from shenfun.tensorproductspace import TensorProductSpace
from shenfun import inner, div, grad, TestFunction, TrialFunction, Function, \
    project
from mpi4py import MPI

comm = MPI.COMM_WORLD

# Collect basis and solver from either Chebyshev or Legendre submodules
basis = sys.argv[-1] if len(sys.argv) == 2 else 'chebyshev'
shen = importlib.import_module('.'.join(('shenfun', basis)))
Basis = shen.bases.ShenDirichletBasis
Solver = shen.la.Helmholtz

# Use sympy to compute a rhs, given an analytical solution
x, y = symbols("x,y")
ue = (cos(4*y) + sin(2*x))*(1-x**2)
fe = ue.diff(x, 2) + ue.diff(y, 2)

# Lambdify for faster evaluation
ul = lambdify((x, y), ue, 'numpy')
fl = lambdify((x, y), fe, 'numpy')

# Size of discretization
N = (32, 32)

SD = Basis(N[0])
K1 = R2CBasis(N[1])
T = TensorProductSpace(comm, (SD, K1))
X = T.local_mesh(True) # With broadcasting=True the shape of X is local_shape, even though the number of datapoints are still the same as in 1D
u = TrialFunction(T)
v = TestFunction(T)

# Get f on quad points
fj = fl(*X)

# Compute right hand side of Poisson equation
f_hat = inner(v, fj)
if basis == 'legendre':
    f_hat *= -1.

# Get left hand side of Poisson equation
if basis == 'chebyshev':
    matrices = inner(v, div(grad(u)))
else:
    matrices = inner(grad(v), grad(u))

# Create Helmholtz linear algebra solver
H = Solver(**matrices, local_shape=T.local_shape())

# Solve and transform to real space
u_hat = Function(T)           # Solution spectral space
u_hat = H(u_hat, f_hat)       # Solve
uq = Function(T, False)
uq = T.backward(u_hat, uq)

# Compare with analytical solution
uj = ul(*X)
print(abs(uj-uq).max())
assert np.allclose(uj, uq)

plt.figure()
plt.contourf(X[0], X[1], uq)
plt.colorbar()

plt.figure()
plt.contourf(X[0], X[1], uj)
plt.colorbar()

plt.figure()
plt.contourf(X[0], X[1], uq-uj)
plt.colorbar()
plt.title('Error')

plt.show()
