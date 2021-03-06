#pylint: disable=missing-docstring

import numpy as np
from .bases import *
from .matrices import *

def energy_fourier(u, T):
    """Compute the energy of u using Parceval's theorem

    Parameters
    ----------
        u : Array
            The Fourier coefficients
        T : TensorProductSpace

    """
    if not hasattr(T, 'comm'):
        # Just a 1D basis
        assert u.ndim == 1
        if isinstance(T, fourier.bases.R2CBasis):
            result = (2*np.sum(abs(u[1:-1])**2) +
                      np.sum(abs(u[0])**2) +
                      np.sum(abs(u[-1])**2))
        else:
            result = np.sum(abs(u)**2)
        return result

    comm = T.comm
    assert np.all([isinstance(base, FourierBase) for base in T.bases])
    if isinstance(T.bases[-1], R2CBasis):
        if T.forward.output_pencil.subcomm[-1].Get_size() == 1:
            result = (2*np.sum(abs(u[..., 1:-1])**2) +
                      np.sum(abs(u[..., 0])**2) +
                      np.sum(abs(u[..., -1])**2))

        else:
            # Data not aligned along last dimension. Need to check about 0 and -1
            result = 2*np.sum(abs(u[..., 1:-1])**2)
            if T.local_slice(True)[-1].start == 0:
                result += np.sum(abs(u[..., 0])**2)
            else:
                result += 2*np.sum(abs(u[..., 0])**2)
            if T.local_slice(True)[-1].stop == T.spectral_shape()[-1]:
                result += np.sum(abs(u[..., -1])**2)
            else:
                result += 2*np.sum(abs(u[..., -1])**2)
    else:
        result = np.sum(abs(u[...])**2)

    result = comm.allreduce(result)
    return result

