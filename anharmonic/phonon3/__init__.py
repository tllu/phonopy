import numpy as np
from anharmonic.phonon3.imag_self_energy import ImagSelfEnergy
from anharmonic.phonon3.interaction import Interaction
from anharmonic.phonon3.conductivity_RTA import conductivity_RTA
from anharmonic.phonon3.jointDOS import get_jointDOS
from anharmonic.phonon3.gruneisen import Gruneisen
from anharmonic.file_IO import write_kappa_to_hdf5
from anharmonic.file_IO import read_gamma_from_hdf5, write_damping_functions, write_linewidth

class Phono3py:
    def __init__(self,
                 fc3,
                 supercell,
                 primitive,
                 mesh,
                 band_indices=None,
                 frequency_factor_to_THz=None,
                 is_nosym=False,
                 symmetrize_fc3_q=False,
                 symprec=1e-5,
                 cutoff_frequency=1e-4,
                 log_level=0,
                 lapack_zheev_uplo='L'):

        self._fc3 = fc3
        self._supercell = supercell
        self._primitive = primitive
        self._mesh = mesh
        if band_indices is None:
            self._band_indices = [
                np.arange(primitive.get_number_of_atoms() * 3)]
        else:
            self._band_indices = band_indices
        self._frequency_factor_to_THz = frequency_factor_to_THz
        self._is_nosym = is_nosym
        self._symmetrize_fc3_q = symmetrize_fc3_q
        self._symprec = symprec
        self._cutoff_frequency = cutoff_frequency
        self._log_level = log_level
        self._kappa = None
        self._gamma = None

        self._band_indices_flatten = np.intc(
            [x for bi in self._band_indices for x in bi])
        self._interaction = Interaction(
            fc3,
            supercell,
            primitive,
            mesh,
            band_indices=self._band_indices_flatten,
            frequency_factor_to_THz=self._frequency_factor_to_THz,
            symprec=self._symprec,
            cutoff_frequency=self._cutoff_frequency,
            is_nosym=self._is_nosym,
            symmetrize_fc3_q=self._symmetrize_fc3_q,
            lapack_zheev_uplo=lapack_zheev_uplo)
        
    def set_dynamical_matrix(self,
                             fc2,
                             supercell,
                             primitive,
                             nac_params=None,
                             nac_q_direction=None,
                             frequency_scale_factor=None):
        self._interaction.set_dynamical_matrix(
            fc2,
            supercell,
            primitive,
            nac_params=nac_params,
            frequency_scale_factor=frequency_scale_factor)
        self._interaction.set_nac_q_direction(nac_q_direction=nac_q_direction)
                           
    def get_imag_self_energy(self,
                             grid_points,
                             frequency_step=1.0,
                             sigmas=[0.1],
                             temperatures=[0.0],
                             filename=None):
        ise = ImagSelfEnergy(self._interaction)
        for gp in grid_points:
            ise.set_grid_point(gp)
            ise.run_interaction()
            for sigma in sigmas:
                ise.set_sigma(sigma)
                for t in temperatures:
                    ise.set_temperature(t)
                    max_freq = (np.amax(self._interaction.get_phonons()[0]) * 2
                                + sigma * 4)
                    fpoints = np.arange(0, max_freq + frequency_step / 2,
                                        frequency_step)
                    ise.set_fpoints(fpoints)
                    ise.run()
                    gamma = ise.get_imag_self_energy()

                    for i, bi in enumerate(self._band_indices):
                        pos = 0
                        for j in range(i):
                            pos += len(self._band_indices[j])

                        write_damping_functions(
                            gp,
                            bi,
                            self._mesh,
                            fpoints,
                            gamma[:, pos:(pos + len(bi))].sum(axis=1) / len(bi),
                            sigma=sigma,
                            temperature=t,
                            filename=filename)

    def get_linewidth(self,
                      grid_points,
                      sigmas=[0.1],
                      t_max=1500,
                      t_min=0,
                      t_step=10,
                      filename=None):
        ise = ImagSelfEnergy(self._interaction)
        temperatures = np.arange(t_min, t_max + t_step / 2.0, t_step)
        for gp in grid_points:
            ise.set_grid_point(gp)
            ise.run_interaction()
            for sigma in sigmas:
                ise.set_sigma(sigma)
                gamma = np.zeros((len(temperatures),
                                  len(self._band_indices_flatten)),
                                 dtype='double')
                for i, t in enumerate(temperatures):
                    ise.set_temperature(t)
                    ise.run()
                    gamma[i] = ise.get_imag_self_energy()

                for i, bi in enumerate(self._band_indices):
                    pos = 0
                    for j in range(i):
                        pos += len(self._band_indices[j])

                    write_linewidth(gp,
                                    bi,
                                    temperatures,
                                    gamma[:, pos:(pos+len(bi))],
                                    self._mesh,
                                    sigma=sigma,
                                    filename=filename)


    def get_thermal_conductivity(self,
                                 sigmas=[0.1],
                                 t_max=1500,
                                 t_min=0,
                                 t_step=10,
                                 grid_points=None,
                                 mesh_divisors=None,
                                 coarse_mesh_shifts=None,
                                 no_kappa_stars=False,
                                 gv_delta_q=1e-4, # for group velocity
                                 write_gamma=False,
                                 read_gamma=False,
                                 write_amplitude=False,
                                 read_amplitude=False,
                                 filename=None):
        br = conductivity_RTA(self._interaction,
                              sigmas=sigmas,
                              t_max=t_max,
                              t_min=t_min,
                              t_step=t_step,
                              mesh_divisors=mesh_divisors,
                              coarse_mesh_shifts=coarse_mesh_shifts,
                              no_kappa_stars=no_kappa_stars,
                              gv_delta_q=gv_delta_q,
                              log_level=self._log_level,
                              filename=filename)
        br.set_grid_points(grid_points)

        if read_gamma:
            gamma = []
            for sigma in sigmas:
                gamma_at_sigma = []
                for i, gp in enumerate(br.get_grid_points()):
                    gamma_at_sigma.append(read_gamma_from_hdf5(
                        br.get_mesh_numbers(),
                        mesh_divisors=br.get_mesh_divisors(),
                        grid_point=gp,
                        sigma=sigma,
                        filename=filename))
                gamma.append(gamma_at_sigma)
            br.set_gamma(np.double(gamma))

        br.calculate_kappa(write_amplitude=write_amplitude,
                           read_amplitude=read_amplitude,
                           write_gamma=write_gamma)        
        mode_kappa = br.get_kappa()
        gamma = br.get_gamma()

        if grid_points is None:
            temperatures = br.get_temperatures()
            for i, sigma in enumerate(sigmas):
                kappa = mode_kappa[i].sum(axis=2).sum(axis=0)
                print "----------- Thermal conductivity (W/m-k) for",
                print "sigma=%s -----------" % sigma
                print ("#%6s     " + " %-9s" * 6) % ("T(K)", "xx", "yy", "zz",
                                                    "yz", "xz", "xy")
                for t, k in zip(temperatures, kappa):
                    print ("%7.1f" + " %9.3f" * 6) % ((t,) + tuple(k))
                print
                write_kappa_to_hdf5(gamma[i],
                                    temperatures,
                                    br.get_mesh_numbers(),
                                    frequency=br.get_frequencies(),
                                    group_velocity=br.get_group_velocities(),
                                    heat_capacity=br.get_mode_heat_capacities(),
                                    kappa=kappa,
                                    qpoint=br.get_qpoints(),
                                    weight=br.get_grid_weights(),
                                    mesh_divisors=br.get_mesh_divisors(),
                                    sigma=sigma,
                                    filename=filename)

        self._kappa = mode_kappa
        self._gamma = gamma

    def solve_dynamical_matrix(self, q):
        """Only for test phonopy zheev wrapper"""
        import anharmonic._phono3py as phono3c
        dm = self._pp.get_dynamical_matrix()
        dm.set_dynamical_matrix(q)
        dynmat = dm.get_dynamical_matrix()
        eigvals = np.zeros(len(dynmat), dtype=float)
        phono3c.zheev(dynmat, eigvals)
        
        for f, row in zip(np.sqrt(abs(eigvals)) * self._factor *
                          np.sign(eigvals), dynmat.T):
            print f
            print row
        

    
class JointDOS:
    def __init__(self,
                 supercell,
                 primitive,
                 mesh,
                 fc2,
                 nac_params=None,
                 sigma=None,
                 frequency_step=None,
                 factor=None,
                 frequency_factor=None,
                 frequency_scale_factor=None,
                 is_nosym=False,
                 symprec=1e-5,
                 log_level=0):
        self._supercell = supercell
        self._primitive = primitive
        self._mesh = mesh
        self._fc2 = fc2
        self._nac_params = nac_params
        self._sigma = sigma
        self._frequency_step = frequency_step
        self._factor = factor
        self._frequency_factor = frequency_factor
        self._frequency_scale_factor = frequency_scale_factor
        self._is_nosym = is_nosym
        self._symprec = symprec
        self._log_level = log_level

    def get_jointDOS(self, grid_points, filename=None):
        get_jointDOS(grid_points,
                     self._mesh,
                     self._primitive,
                     self._supercell,
                     self._fc2,
                     nac_params=self._nac_params,
                     sigma=self._sigma,
                     frequency_step=self._frequency_step,
                     factor=self._factor,
                     frequency_factor=self._frequency_factor,
                     frequency_scale=self._frequency_scale_factor,
                     is_nosym=self._is_nosym,
                     symprec=self._symprec,
                     filename=filename,
                     log_level=self._log_level)


def get_gruneisen_parameters(fc2,
                             fc3,
                             supercell,
                             primitive,
                             nac_params=None,
                             nac_q_direction=None,
                             ion_clamped=False,
                             factor=None,
                             symprec=1e-5):
    return Gruneisen(fc2,
                     fc3,
                     supercell,
                     primitive,
                     nac_params=nac_params,
                     nac_q_direction=nac_q_direction,
                     ion_clamped=ion_clamped,
                     factor=factor,
                     symprec=symprec)
