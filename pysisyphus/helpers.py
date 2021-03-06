from collections import namedtuple
import itertools as it
import logging
from math import log
import os
from pathlib import Path
import re

import numpy as np
import scipy as sp
from scipy.optimize import linear_sum_assignment
from scipy.spatial.distance import cdist

from pysisyphus.constants import ANG2BOHR, AU2KJPERMOL
from pysisyphus.Geometry import Geometry
from pysisyphus.helpers_pure import eigval_to_wavenumber
from pysisyphus.io import geom_from_pdb, geom_from_cjson, save_hessian as save_h5_hessian
from pysisyphus.xyzloader import parse_xyz_file, parse_trj_file, make_trj_str


THIS_DIR = Path(os.path.abspath(os.path.dirname(__file__)))


def geom_from_xyz_file(xyz_fn, coord_type="cart", **coord_kwargs):
    kwargs = {
        "coord_type": coord_type,
    }
    kwargs.update(coord_kwargs)
    xyz_fn = str(xyz_fn)
    if xyz_fn.startswith("lib:"):
        # Drop lib: part
        return geom_from_library(xyz_fn[4:], **kwargs)
    atoms, coords, comment = parse_xyz_file(xyz_fn, with_comment=True)
    coords *= ANG2BOHR
    geom = Geometry(atoms, coords.flatten(),
                    comment=comment,
                    **kwargs,
    )
    return geom


def geoms_from_trj(trj_fn, first=None, coord_type="cart", **coord_kwargs):
    trj_fn = str(trj_fn)
    kwargs = {
        "coord_type": coord_type,
    }
    kwargs.update(coord_kwargs)
    if trj_fn.startswith("lib:"):
        # Drop lib: part
        return geom_from_library(trj_fn[4:], **kwargs)[:first]
    atoms_coords_comments = parse_trj_file(trj_fn, with_comments=True)[:first]
    geoms = [Geometry(atoms, coords.flatten()*ANG2BOHR,
                      comment=comment,
                      **kwargs
             )
             for atoms, coords, comment in atoms_coords_comments
    ]
    return geoms


def geom_loader(fn, coord_type="cart", **coord_kwargs):
    fn = str(fn)

    if fn.startswith("lib:"):
        fn = str(THIS_DIR / "../xyz_files/" / fn[4:])

    kwargs = {
        "coord_type": coord_type,
    }
    kwargs.update(coord_kwargs)
    if fn.endswith(".xyz"):
        return geom_from_xyz_file(fn, **kwargs)
    elif fn.endswith(".trj"):
        return geoms_from_trj(fn, **kwargs)
    elif fn.endswith(".pdb"):
        return geom_from_pdb(fn, **kwargs)
    elif fn.endswith(".cjson"):
        return geom_from_cjson(fn, **kwargs)
    else:
        raise Exception("Unknown filetype!")


def geom_from_library(xyz_fn, coord_type="cart", **coord_kwargs):
    xyz_dir = THIS_DIR / "../xyz_files/"
    xyz_fn = xyz_dir / xyz_fn
    return geom_loader(xyz_fn,
                       coord_type=coord_type,
                       **coord_kwargs,
    )


def get_baker_geoms(**kwargs):
    baker_path = THIS_DIR / "../xyz_files/baker"
    xyz_fns = baker_path.glob("*.xyz")
    geoms = {
        xyz_fn.name: geom_from_xyz_file(xyz_fn, **kwargs) for xyz_fn in xyz_fns
    }
    # del geoms["acetylene.xyz"]
    # From 10.1002/jcc.540140910
    sto3g_energies = {
        "water.xyz": -74.96590,
        "ammonia.xyz": -55.45542,
        "ethane.xyz": -78.30618,
        "acetylene.xyz": -75.85625,
        "allene.xyz": -114.42172,
        "hydroxysulphane.xyz": -468.12592,
        "benzene.xyz": -227.89136,
        "methylamine.xyz": -94.01617,
        "ethanol.xyz": -152.13267,
        "acetone.xyz": -189.53603,
        "disilylether.xyz": -648.58003,
        "135trisilacyclohexane.xyz": -976.13242,
        "benzaldehyde.xyz": -339.12084,
        "13difluorobenzene.xyz": -422.81106,
        "135trifluorobenzene.xyz": -520.27052,
        "neopentane.xyz": -194.04677,
        "furan.xyz": -225.75126,
        "naphthalene.xyz": -378.68685,
        "15difluoronaphthalene.xyz": -573.60633,
        "2hydroxybicyclopentane.xyz": -265.46482,
        "achtar10.xyz": -356.28265,
        "acanil01.xyz": -432.03012,
        "benzidine.xyz": -563.27798,
        "pterin.xyz": -569.84884,
        "difuropyrazine.xyz": -556.71910,
        "mesityloxide.xyz": -304.05919,
        "histidine.xyz": -538.54910,
        "dimethylpentane.xyz": -271.20088,
        "caffeine.xyz": -667.73565,
        "menthone.xyz": -458.44639,
    }
    # Join both dicts
    baker_dict = {}
    for name, geom in geoms.items():
        try:
            baker_dict[name] = (geom, sto3g_energies[name])
        except KeyError:
            pass
    return baker_dict


def get_baker_ts_geoms(**kwargs):
    baker_ts_path = THIS_DIR / "../xyz_files/baker_ts"
    xyz_fns = baker_ts_path.glob("*.xyz")
    geoms = {
        xyz_fn.name: geom_from_xyz_file(xyz_fn, **kwargs) for xyz_fn in xyz_fns
        if not ("downhill" in xyz_fn.name)
    }
    # From 10.1002/(SICI)1096-987X(199605)17:7<888::AID-JCC12>3.0.CO;2-7
    meta_data = {
        "01_hcn.xyz": (0, 1, -92.24604),
        "02_hcch.xyz": (0, 1, -76.29343),
        "03_h2co.xyz": (0, 1, -113.05003),
        "04_ch3o.xyz": (0, 2, -113.69365),
        "05_cyclopropyl.xyz": (0, 2, -115.72100),
        "06_bicyclobutane.xyz": (0, 1, -153.90494),
        "07_bicyclobutane.xyz": (0, 1, -153.89754),
        "08_formyloxyethyl.xyz": (0, 2, -264.64757),
        "09_parentdieslalder.xyz": (0, 1, -231.60321),
        # 10 and 11 don't have any imaginary frequencies at the given
        # geometry, so they may be skipped.
        "10_tetrazine.xyz": (0, 1, -292.81026),
        "11_trans_butadiene.xyz": (0, 1, -154.05046),
        "12_ethane_h2_abstraction.xyz": (0, 1, -78.54323),
        "13_hf_abstraction.xyz": (0, 1, -176.98453),
        "14_vinyl_alcohol.xyz": (0, 1, -151.91310),
        # 15 does not have an imaginary mode in cartesian coordinates
        "15_hocl.xyz": (0, 1, -596.87865),
        "16_h2po4_anion.xyz": (-1, 1, -637.92388),
        "17_claisen.xyz": (0, 1, -267.23859),
        "18_silyene_insertion.xyz": (0, 1, -367.20778),
        "19_hnccs.xyz": (0, 1, -525.43040),
        # The energy given in the paper (-168.24752 au) is the correct one
        # if one forms the central (0,1) bond (0-based indexing). If this
        # bond is missing, as it is if we autogenerate with bond-factor=1.3
        # then a TS with -168.241392 will be found.
        # For now we will use the original value from the paper.
        "20_hconh3_cation.xyz": (1, 1, -168.24752),
        "21_acrolein_rot.xyz": (0, 1, -189.67574),
        # This energy will be obtained for a planar TS, without symmetry
        # restrictions the TS will relax to -242.25695787.
        "22_hconhoh.xyz": (0, 1, -242.25529),
        "23_hcn_h2.xyz": (0, 1, -93.31114),
        "24_h2cnh.xyz": (0, 1, -93.33296),
        "25_hcnh2.xyz": (0, 1, -93.28172),
    }
    return geoms, meta_data


def get_baker_ts_geoms_flat(**kwargs):
     geoms, meta_data = get_baker_ts_geoms(**kwargs)
     # Key: (geometry, charge, mult, ref_energy)
     return [(mol,) + (geom, ) + meta_data[mol] for mol, geom in geoms.items()]


def get_baker_opt_ts_geoms(**kwargs):
    meta_data = {
        "01_hcn_opt_ts.xyz": (0, 1),
        # "02_hcch_opt_ts.xyz": (0, 1),
        "03_h2co_opt_ts.xyz": (0, 1),
        "04_ch3o_opt_ts.xyz": (0, 2),
        "05_cyclopropyl_opt_ts.xyz": (0, 2),
        "06_bicyclobutane_opt_ts.xyz": (0, 1),
        "07_bicyclobutane_opt_ts.xyz": (0, 1),
        "08_formyloxyethyl_opt_ts.xyz": (0, 2),
        # "09_parentdieslalder_opt_ts.xyz": (0, 1),
        # "10_tetrazine_opt_ts.xyz": (0, 1),
        # "11_trans_butadiene_opt_ts.xyz": (0, 1),
        # "12_ethane_h2_abstraction_opt_ts.xyz": (0, 1),
        "13_hf_abstraction_opt_ts.xyz": (0, 1),
        "14_vinyl_alcohol_opt_ts.xyz": (0, 1),
        # "15_hocl_opt_ts.xyz": (0, 1),
        "16_h2po4_anion_opt_ts.xyz": (-1, 1),
        # "17_claisen_opt_ts.xyz": (0, 1),
        "18_silyene_insertion_opt_ts.xyz": (0, 1),
        "19_hnccs_opt_ts.xyz": (0, 1),
        "20_hconh3_cation_opt_ts.xyz": (1, 1),
        "21_acrolein_rot_opt_ts.xyz": (0, 1),
        # "22_hconhoh_opt_ts.xyz": (0, 1),
        "23_hcn_h2_opt_ts.xyz": (0, 1),
        "24_h2cnh_opt_ts.xyz": (0, 1),
        "25_hcnh2_opt_ts.xyz": (0, 1),
    }
    baker_ts_path = THIS_DIR / "../xyz_files/baker_opt_ts"
    geoms = {
        xyz_fn: geom_from_xyz_file(baker_ts_path / xyz_fn, **kwargs)
        for xyz_fn in meta_data.keys()
    }

    return geoms, meta_data


def get_baker_ts_data():
    # From 10.1002/(SICI)1096-987X(199605)17:7<888::AID-JCC12>3.0.CO;2-7
    data = {
        "01_hcn.xyz": (0, 1, -92.24604),
        "02_hcch.xyz": (0, 1, -76.29343),
        "03_h2co.xyz": (0, 1, -113.05003),
        "04_ch3o.xyz": (0, 2, -113.69365),
        "05_cyclopropyl.xyz": (0, 2, -115.72100),
        "06_bicyclobutane.xyz": (0, 1, -153.90494),
        "07_bicyclobutane.xyz": (0, 1, -153.89754),
        "08_formyloxyethyl.xyz": (0, 2, -264.64757),
        "09_parentdieslalder.xyz": (0, 1, -231.60321),
        # 10 and 11 don't have any imaginary frequencies at the given
        # geometry, so they may be skipped.
        "10_tetrazine.xyz": (0, 1, -292.81026),
        "11_trans_butadiene.xyz": (0, 1, -154.05046),
        "12_ethane_h2_abstraction.xyz": (0, 1, -78.54323),
        "13_hf_abstraction.xyz": (0, 1, -176.98453),
        "14_vinyl_alcohol.xyz": (0, 1, -151.91310),
        # 15 does not have an imaginary mode in cartesian coordinates
        "15_hocl.xyz": (0, 1, -596.87865),
        "16_h2po4_anion.xyz": (-1, 1, -637.92388),
        "17_claisen.xyz": (0, 1, -267.23859),
        "18_silyene_insertion.xyz": (0, 1, -367.20778),
        "19_hnccs.xyz": (0, 1, -525.43040),
        # The energy given in the paper (-168.24752 au) is the correct one
        # if one forms the central (0,1) bond (0-based indexing). If this
        # bond is missing, as it is if we autogenerate with bond-factor=1.3
        # then a TS with -168.241392 will be found.
        # For now we will use the original value from the paper.
        "20_hconh3_cation.xyz": (1, 1, -168.24752),
        "21_acrolein_rot.xyz": (0, 1, -189.67574),
        # This energy will be obtained for a planar TS, without symmetry
        # restrictions the TS will relax to -242.25695787.
        "22_hconhoh.xyz": (0, 1, -242.25529),
        "23_hcn_h2.xyz": (0, 1, -93.31114),
        "24_h2cnh.xyz": (0, 1, -93.33296),
        "25_hcnh2.xyz": (0, 1, -93.28172),
    }
    return data


def align_geoms(geoms):
    # http://nghiaho.com/?page_id=671#comment-559906
    first_geom = geoms[0]
    coords3d = first_geom.coords3d
    centroid = coords3d.mean(axis=0)
    last_centered = coords3d - centroid
    first_geom.coords3d = last_centered
    atoms_per_image = len(first_geom.atoms)

    # Don't rotate the first image, so just add identitiy matrices
    # for every atom.
    rot_mats = [np.eye(3)]*atoms_per_image
    for i, geom in enumerate(geoms[1:], 1):
        coords3d = geom.coords3d
        centroid = coords3d.mean(axis=0)
        # Center next image
        centered = coords3d - centroid
        tmp_mat = centered.T.dot(last_centered)
        U, W, Vt = np.linalg.svd(tmp_mat)
        rot_mat = U.dot(Vt)
        # Avoid reflections
        if np.linalg.det(rot_mat) < 0:
            U[:, -1] *= -1
            rot_mat = U.dot(Vt)
        # Rotate the coords
        rotated3d = centered.dot(rot_mat)
        geom.coords3d = rotated3d
        last_centered = rotated3d
        # Append one rotation matrix per atom
        rot_mats.extend([rot_mat]*atoms_per_image)
    return rot_mats


def procrustes(geometry):
    # http://nghiaho.com/?page_id=671#comment-559906
    image0 = geometry.images[0]
    coords3d = image0.coords3d
    centroid = coords3d.mean(axis=0)
    last_centered = coords3d - centroid
    geometry.set_coords_at(0, last_centered.flatten())
    atoms_per_image = len(image0.atoms)

    # Don't rotate the first image, so just add identitiy matrices
    # for every atom.
    rot_mats = [np.eye(3)]*atoms_per_image
    for i, image in enumerate(geometry.images[1:], 1):
        coords3d = image.coords3d
        centroid = coords3d.mean(axis=0)
        # Center next image
        centered = coords3d - centroid
        tmp_mat = centered.T.dot(last_centered)
        U, W, Vt = np.linalg.svd(tmp_mat)
        rot_mat = U.dot(Vt)
        # Avoid reflections
        if np.linalg.det(rot_mat) < 0:
            U[:, -1] *= -1
            rot_mat = U.dot(Vt)
        # Rotate the coords
        rotated3d = centered.dot(rot_mat)
        geometry.set_coords_at(i, rotated3d.flatten())
        last_centered = rotated3d
        # Append one rotation matrix per atom
        rot_mats.extend([rot_mat]*atoms_per_image)
    return rot_mats


def align_coords(coords_list):
    coords_list = np.array(coords_list)
    coord_num = len(coords_list)
    aligned_coords = np.empty_like(coords_list).reshape(coord_num, -1, 3)

    coords0 = coords_list[0]
    coords0_3d = coords0.reshape(-1, 3)
    centroid = coords0_3d.mean(axis=0)
    prev_centered = coords0_3d - centroid
    aligned_coords[0] = prev_centered

    for i, coords in enumerate(coords_list[1:], 1):
        coords3d = coords.reshape(-1, 3)
        centroid = coords3d.mean(axis=0)
        # Center next image
        centered = coords3d - centroid
        tmp_mat = centered.T.dot(prev_centered)
        U, W, Vt = np.linalg.svd(tmp_mat)
        rot_mat = U.dot(Vt)
        # Avoid reflections
        if np.linalg.det(rot_mat) < 0:
            U[:, -1] *= -1
            rot_mat = U.dot(Vt)
        # Rotate the coords
        rotated3d = centered.dot(rot_mat)
        aligned_coords[i] = rotated3d
        prev_centered = rotated3d
    aligned_coords.reshape(coord_num, -1)
    return aligned_coords


# def rmsd(coord_1, coord_2):
    # aligned_1, aligned_2 = align_coords((coord_1, coord_2))
    # result = np.sqrt(np.mean(aligned_1 - aligned_2)**2)
    # return result


def fit_rigid(geometry, vectors=(), vector_lists=(), hessian=None):
    rotated_vector_lists = list()
    rotated_hessian = None

    rot_mats = procrustes(geometry)
    G = sp.linalg.block_diag(*rot_mats)
    rotated_vectors = [vec.dot(G) for vec in vectors]
    for vl in vector_lists:
        rvl = [vec.dot(G) for vec in vl]
        rotated_vector_lists.append(rvl)

    if hessian is not None:
        # rotated_hessian = G.dot(hessian).dot(G.T)
        # rotated_hessian = G.T.dot(hessian).dot(G)
        rotated_hessian = G*hessian*G.T
    return rotated_vectors, rotated_vector_lists, rotated_hessian


def chunks(l, n):
    """Yield successive n-sized chunks from l.
    https://stackoverflow.com/a/312464
    """
    for i in range(0, len(l), n):
        yield l[i:i + n]


def slugify_worker(dask_worker):
    slug = re.sub("tcp://", "host_", dask_worker)
    slug = re.sub("\.", "_", slug)
    slug = re.sub(":", "-", slug)
    return slug


def match_geoms(ref_geom, geom_to_match, hydrogen=False):
    """
    See
        [1] 10.1021/ci400534h
        [2] 10.1021/acs.jcim.6b00516
    """

    logging.warning("helpers.match_geoms is deprecated!"
                    "Use stocastic.align.match_geom_atoms instead!")

    assert len(ref_geom.atoms) == len(geom_to_match.atoms), \
        "Atom numbers don't match!"

    ref_coords, _ = ref_geom.coords_by_type
    coords_to_match, inds_to_match = geom_to_match.coords_by_type
    atoms = ref_coords.keys()
    for atom in atoms:
        # Only match hydrogens if explicitly requested
        if atom == "H" and not hydrogen:
            continue
        print("atom", atom)
        ref_coords_for_atom = ref_coords[atom]
        coords_to_match_for_atom = coords_to_match[atom]
        # Pairwise distances between two collections
        # Atoms of ref_geom are along the rows, atoms of geom_to_match
        # along the columns.
        cd = cdist(ref_coords_for_atom, coords_to_match_for_atom)
        print(cd)
        # Hungarian method, row_inds are returned already sorted.
        row_inds, col_inds = linear_sum_assignment(cd)
        print("col_inds", col_inds)
        old_inds = inds_to_match[atom]
        new_inds = old_inds[col_inds]
        print("old_inds", old_inds)
        print("new_inds", new_inds)
        new_coords_for_atom = coords_to_match_for_atom[new_inds]
        # print(ref_coords_for_atom)
        # print(new_coords_for_atom)
        # print(ref_coords_for_atom-new_coords_for_atom)
        # Update coordinates
        print("old coords")
        c3d = geom_to_match.coords3d
        print(c3d)
        # Modify the coordinates directly
        c3d[old_inds] = new_coords_for_atom
        # coords_to_match[atom] = coords_to_match_for_atom[new_inds]


def check_for_stop_sign():
    stop_signs = ("stop", "STOP")
    stop_sign_found = False

    for ss in stop_signs:
        if os.path.exists(ss):
            print("Found stop sign. Stopping run.")
            os.remove(ss)
            stop_sign_found = True
    return stop_sign_found


def check_for_end_sign():
    signs = ("stop", "converged", )
    sign_found = False

    for sign in signs:
        if os.path.exists(sign):
            print(f"Found sign '{sign}'. Ending run.")
            os.remove(sign)
            sign_found = sign
    return sign_found


def index_array_from_overlaps(overlaps, axis=1):
    """It is assumed that the overlaps between two points with indices
    i and j with (j > i) are computed and that i changes along the first
    axis (axis=0) and j changes along the second axis (axis=1).

    So the first row of the overlap matrix (overlaps[0]) should contain
    the overlaps between state 0 at index i and all states at index j.

    argmax along axis 1 returns the indices of the most overlapping states
    at index j with the states at index i, given by the item index in the
    indices array. E.g.:
        [0 1 3 2] indicates a root flip in a system with four states when
        going from index i to index j. Root 2 at i became root 3 at j and
        vice versa.
    """
    # indices = np.argmax(overlaps**2, axis=1)
    indices = np.argmax(np.abs(overlaps), axis=1)
    return indices


def np_print(func, precision=2, suppress=True, linewidth=120):
    def wrapped(*args, **kwargs):
        org_print_dict = dict(np.get_printoptions())
        np.set_printoptions(suppress=suppress,
                            precision=precision,
                            linewidth=linewidth)
        result = func(*args, **kwargs)
        np.set_printoptions(**org_print_dict)
        return result
    return wrapped


def confirm_input(message):
    full_message = message + " (yes/no)\n"
    inp = input(full_message)
    return inp == "yes"


def get_geom_getter(ref_geom, calc_setter):
    def geom_from_coords(coords):
        new_geom = ref_geom.copy()
        new_geom.coords = coords
        new_geom.set_calculator(calc_setter())
        return new_geom
    return geom_from_coords


def get_coords_diffs(coords, align=False):
    if align:
        coords = align_coords(coords)
    cds = [0, ]
    for i in range(len(coords)-1):
        diff = np.linalg.norm(coords[i+1]-coords[i])
        cds.append(diff)
    cds = np.cumsum(cds)
    cds /= cds.max()
    return cds


def shake_coords(coords, scale=0.1, seed=None):
    if seed:
        np.random.seed(seed)
    offset = np.random.normal(scale=scale, size=coords.size)
    return coords + offset


def highlight_text(text, width=80, level=0):
    levels = {
        #  horizontal    
        #        vertical
        0: ("#", "#"),
        1: ("-", "|"),
        } 
    full_length = len(text) + 4
    pad_len = width - full_length
    pad_len = (pad_len - (pad_len % 2)) // 2
    pad = " " * pad_len
    hchar, vchar = levels[level]
    full_row = hchar * full_length
    highlight = f"""{pad}{full_row}\n{pad}{vchar} {text.upper()} {vchar}\n{pad}{full_row}"""
    return highlight


def rms(arr):
    return np.sqrt(np.mean(arr**2))


def complete_fragments(atoms, fragments):
    lengths = [len(frag) for frag in fragments]

    frag_atoms = sum(lengths)

    all_inds = set(range(len(atoms)))
    frag_inds = set(it.chain(*fragments))
    rest_inds = all_inds - frag_inds

    assert len(frag_inds) + len(rest_inds) == len(atoms)
    assert frag_inds & rest_inds == set()

    if rest_inds:
        fragments.append(tuple(rest_inds))
    fragments = tuple([tuple(frag) for frag in fragments])

    return fragments


FinalHessianResult = namedtuple("FinalHessianResult",
                                "neg_eigvals eigvals nus imag_fns",
)


def do_final_hessian(geom, save_hessian=True, write_imag_modes=False,
                     prefix=""):
    print(highlight_text("Hessian at final geometry", level=1))
    print()

    # TODO: Add cartesian_hessian property to Geometry to avoid
    # accessing a "private" attribute.
    hessian = geom.cart_hessian
    print("... mass-weighing cartesian hessian")
    mw_hessian = geom.mass_weigh_hessian(hessian)
    print("... doing Eckart-projection")
    proj_hessian = geom.eckart_projection(mw_hessian)
    eigvals, eigvecs = np.linalg.eigh(proj_hessian)
    ev_thresh = -1e-6

    neg_inds = eigvals < ev_thresh
    neg_eigvals = eigvals[neg_inds]
    neg_num = sum(neg_inds)
    eigval_str = np.array2string(eigvals[:10], precision=4)
    print()
    print("First 10 eigenvalues", eigval_str)
    # print(f"Self found {neg_num} eigenvalue(s) < {ev_thresh}.")
    if neg_num > 0:
        wavenumbers = eigval_to_wavenumber(neg_eigvals)
        wavenum_str = np.array2string(wavenumbers, precision=2)
        print("Imaginary frequencies:", wavenum_str, "cm⁻¹")

    if prefix:
        prefix = f"{prefix}_"

    if save_hessian:
        final_hessian_fn = prefix + "calculated_final_cart_hessian"
        np.savetxt(final_hessian_fn, hessian)
        print()
        print(f"Wrote final (not mass-weighted) hessian to '{final_hessian_fn}'.")

        # Also write HD5 hessian
        final_h5_hessian_fn = prefix + "final_hessian.h5"
        save_h5_hessian(final_h5_hessian_fn, geom)
        print(f"Wrote HD5 Hessian to '{final_h5_hessian_fn}'.")

    imag_fns = list()
    if write_imag_modes:
        imag_modes = imag_modes_from_geom(geom)
        for i, imag_mode in enumerate(imag_modes):
            trj_fn = prefix + f"imaginary_mode_{i:03d}.trj"
            imag_fns.append(trj_fn)
            with open(trj_fn, "w") as handle:
                handle.write(imag_mode.trj_str)
            print(f"Wrote imaginary mode with ṽ={imag_mode.nu:.2f} cm⁻¹ to '{trj_fn}'")

    res = FinalHessianResult(
            neg_eigvals=neg_eigvals,
            eigvals=eigvals,
            nus=eigval_to_wavenumber(eigvals),
            imag_fns=imag_fns,
    )
    return res


def print_barrier(ref_energy, comp_energy, ref_str, comp_str):
    barrier = (ref_energy - comp_energy) * AU2KJPERMOL
    print(f"Barrier between {ref_str} and {comp_str}: {barrier:.1f} kJ mol⁻¹")
    return barrier


def get_tangent_trj_str(atoms, coords, tangent, comment=None,
                        points=10, displ=None):
    if displ is None:
        # Linear equation. Will give displ~3 for 30 atoms and
        # displ ~ 1 for 3 atoms.
        # displ = 2/27 * len(atoms) + 0.78

        # Logarithmic function f(x) = a*log(x) + b
        # f(3) = ~1 and (f30) = ~2 with a = 0.43429 and b = 0.52288
        # I guess this works better, because only some atoms move, even in bigger
        # systems and the log function converges against a certain value, whereas
        # the linear function just keeps growing.
        displ = 0.43429 * log(len(atoms)) + 0.52288
    step_sizes = np.linspace(-displ, displ, 2*points + 1)
    steps = step_sizes[:,None] * tangent
    trj_coords = coords[None,:] + steps
    trj_coords = trj_coords.reshape(step_sizes.size, -1, 3) / ANG2BOHR

    comments = None
    if comment:
        comments = [comment] * step_sizes.size
    trj_str = make_trj_str(atoms, trj_coords, comments=comments)

    return trj_str


def imag_modes_from_geom(geom, freq_thresh=-10, points=10, displ=None):
    NormalMode = namedtuple("NormalMode",
                            "nu mode trj_str"
    )
    # We don't want to do start any calculation here, so we directly access
    # the attribute underlying the geom.hessian property.
    mw_H = geom.eckart_projection(geom.mass_weigh_hessian(geom._hessian))
    eigvals, eigvecs = np.linalg.eigh(mw_H)
    nus = eigval_to_wavenumber(eigvals)
    below_thresh = nus < freq_thresh

    imag_modes = list()
    for nu, eigvec in zip(nus[below_thresh], eigvecs[:, below_thresh].T):
        comment = f"{nu:.2f} cm⁻¹"
        trj_str = get_tangent_trj_str(geom.atoms, geom.cart_coords, eigvec,
                                      comment=comment, points=points, displ=displ)
        imag_modes.append(
            NormalMode(nu=nu,
                       mode=eigvec,
                       trj_str=trj_str,
            )
        )

    return imag_modes
