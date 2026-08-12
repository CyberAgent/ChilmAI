from logging import getLogger

from ortools.sat.python import cp_model

from chilmai.constants import UNMATCHED_DAYCARE_ID
from .helper_functions import *

log = getLogger("chilmai.matching")


class OptimizationFailureError(Exception):
    pass


def CP(
    children_dic,
    daycares_dic,
    families_dic,
    share_bool,
    bp_num=0,
    solver_time=360,
    exclude_bool=True,
    search_depth=5,
):
    model = cp_model.CpModel()
    # generate agents
    children, daycares, families = create_agents(children_dic, daycares_dic, families_dic)

    # generate CP variables
    xfp, xcd, alpha, gamma_fp, gamma_fpd, gamma_fpdg, age_fpd, beta = create_variables(
        children, daycares, families, share_bool, model, exclude_bool, search_depth
    )

    # impose feasibility constraints
    feasibility_constraints(children, daycares, families, share_bool, xfp, xcd, model)

    # impose blocking coalition constraints
    bp = [beta[f.id, p] for f in families for p in range(len(f.pref))]
    model.Add(sum(bp) <= bp_num)

    # objective: maximize the number of matched children
    all_xcd = [
        xcd[c.id, d_id] for c in children for d_id in c.all_daycare_ids if d_id != UNMATCHED_DAYCARE_ID
    ]
    model.Maximize(sum(all_xcd))

    # running time
    import time

    time_sta = time.time()

    # invoke the CP-SAT solver
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 8
    solver.parameters.max_time_in_seconds = solver_time
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise OptimizationFailureError(status)
    log.debug(solver.StatusName(status))
    log.debug(f"Totally matched: {solver.ObjectiveValue()}")

    # ending time
    time_end = time.time()
    tim = time_end - time_sta
    log.debug(f"solver time elapsed {tim}")

    # determine assignment
    outcome_fp = {}
    for f in families:
        for p in range(len(f.pref)):
            outcome_fp[f.id, p] = solver.Value(xfp[f.id, p])
            if outcome_fp[f.id, p] == 1:
                for c_id in f.children:
                    c = get_agent(c_id, children)
                    c.assigned_daycare = c.projected_pref[p]

    # store outcome
    outcome_children_dic = {}
    for c in children:
        outcome_children_dic[c.id] = {}
        if c.assigned_daycare is None:
            c.assigned_daycare = UNMATCHED_DAYCARE_ID
        outcome_children_dic[c.id]["CP"] = c.assigned_daycare

    return outcome_children_dic, outcome_fp, children, daycares, families, status


# create xfp
def creat_variables_xfp(families, model):
    xfp = {}
    for f in families:
        for p in range(len(f.pref)):
            xfp[f.id, p] = model.NewBoolVar(f"xfp_[{f.id}, {p}]")
    return xfp


# create xcd
def creat_variables_xcd(children, daycares, families, xfp, model):
    xcd = {}
    for c in children:
        if len(c.projected_pref) != 0:  # ignore children who do not have preferences
            # only consider daycares which are listed in c.projected_pref, denoted by c.all_daycare_ids
            for d_id in c.all_daycare_ids:
                xcd[c.id, d_id] = model.NewBoolVar(f"xcd_[{c.id}, {d_id}]")
                f_c = get_agent(c.family, families)
                all_positions = c.return_all_positions_of_certain_dacyare_in_projected_pref(d_id)
                model.Add((xcd[c.id, d_id] == (sum(xfp[f_c.id, p] for p in all_positions))))
    return xcd


# create alpha
def creat_variables_alpha(families, xfp, model):
    alpha = {}
    for f in families:
        for p in range(len(f.pref)):
            alpha[f.id, p] = model.NewBoolVar(f"alpha_[{f.id}, {p}]")
            if p == 0:
                # Base case: alpha[f,0] mirrors xfp[f,0]
                model.Add(alpha[f.id, p] == xfp[f.id, p])
            else:
                prev_alpha = alpha[f.id, p - 1]
                current_xfp = xfp[f.id, p]
                # The following three constraints together enforce:
                #   alpha[f,p] == (prev_alpha OR current_xfp)
                # which is equivalent to:
                #   alpha[f,p] == sum(xfp[f,k] for k in range(p+1))
                model.AddImplication(prev_alpha, alpha[f.id, p])
                model.AddImplication(current_xfp, alpha[f.id, p])
                model.AddBoolOr([prev_alpha, current_xfp, alpha[f.id, p].Not()])
    return alpha


# create gamma
# updated on 2024.04.26
def creat_variables_gamma_siblings(
    children,
    daycares,
    share_bool,
    f,
    xcd,
    alpha,
    gamma_fp,
    gamma_fpd,
    gamma_fpdg,
    age_fpd,
    model,
    exclude_bool,
    search_depth,
):
    # for each position p, add one constraint for gamma[f, p]
    for p in range(len(f.pref)):
        for d_id in f.return_daycare_id_for_certain_position(p):  # for each d \in D(f, p)
            d = get_agent(d_id, daycares)
            age_fpd[f.id, p, d_id] = []  # a list of ages that will be used  later
            capacity = d.total_numbers_share if share_bool is True else d.total_numbers

            for g in range(6):
                # number_fpdg : the number of children who i) are from the same family f ii) have grade related to g iii) apply to d w.r.t. \succ_{f, p} and iv) can distribute initial seat if appliable
                number_fpdg = len(
                    f.return_siblings_for_certain_position_daycare_age(
                        p, d_id, g, share_bool, children, daycares
                    )
                )
                # only consider the case where number_fpdg > 0
                if number_fpdg != 0:
                    # variable gamma_fpdg
                    gamma_fpdg[f.id, p, d_id, g] = model.NewBoolVar(
                        f"gamma_fpdg_[{f.id}, {p}, {d_id}, {g}]"
                    )
                    age_fpd[f.id, p, d_id].append(g)  # update age_fpd
                    # find the child c* with the lowest priority who i) is from family f ii) has grade related to g iii) applies to d at \succ_{c, p}
                    worst_id = f.return_lowest_sibling_for_certain_position_daycare_age(
                        p, d_id, g, share_bool, children, daycares
                    )
                    # find all children who i) are not from family f ii) have higher priority than c*
                    children_better = d.return_weak_better_children_than_child_excluding_siblings(
                        worst_id, children, share_bool, exclude_bool, search_depth
                    )
                    # consider the case where no child better than c* exists
                    if len(children_better) == 0:
                        if capacity[g] >= number_fpdg:
                            model.Add(gamma_fpdg[f.id, p, d_id, g] == 1)
                        else:
                            model.Add(gamma_fpdg[f.id, p, d_id, g] == 0)
                    # Channeling constraints: refer to the AAAI 24 paper
                    else:
                        model.Add(
                            (sum(xcd[c_id, d.id] for c_id in children_better) + number_fpdg) <= capacity[g]
                        ).OnlyEnforceIf(gamma_fpdg[f.id, p, d_id, g])
                        model.Add(
                            (sum(xcd[c_id, d.id] for c_id in children_better) + number_fpdg) > capacity[g]
                        ).OnlyEnforceIf(gamma_fpdg[f.id, p, d_id, g].Not())

            # variable \gamma[f,p,d]
            gamma_fpd[f.id, p, d_id] = model.NewBoolVar(f"gamma_fpd_[{f.id}, {p}, {d_id}]")
            # Channeling constraints: refer to the AAAI 24 paper
            model.Add(
                sum(gamma_fpdg[f.id, p, d_id, g] for g in age_fpd[f.id, p, d_id])
                == len(age_fpd[f.id, p, d_id])
            ).OnlyEnforceIf(gamma_fpd[f.id, p, d_id])
            model.Add(
                sum(gamma_fpdg[f.id, p, d_id, g] for g in age_fpd[f.id, p, d_id])
                < len(age_fpd[f.id, p, d_id])
            ).OnlyEnforceIf(gamma_fpd[f.id, p, d_id].Not())

        # variable \gamma[f,p]
        gamma_fp[f.id, p] = model.NewBoolVar(f"gamma_fp_[{f.id}, {p}]")
        id_fp = f.return_daycare_id_for_certain_position(p)
        # Channeling constraints: refer to the AAAI 24 paper
        model.Add(sum(gamma_fpd[f.id, p, d_id] for d_id in id_fp) == len(id_fp)).OnlyEnforceIf(
            gamma_fp[f.id, p]
        )
        model.Add(sum(gamma_fpd[f.id, p, d_id] for d_id in id_fp) < len(id_fp)).OnlyEnforceIf(
            gamma_fp[f.id, p].Not()
        )


# creat gamma
def creat_variables_gamma(
    children, daycares, families, share_bool, xcd, alpha, model, exclude_bool, search_depth
):
    gamma_fpdg = {}
    gamma_fpd = {}
    gamma_fp = {}
    age_fpd = {}

    for f in families:
        creat_variables_gamma_siblings(
            children,
            daycares,
            share_bool,
            f,
            xcd,
            alpha,
            gamma_fp,
            gamma_fpd,
            gamma_fpdg,
            age_fpd,
            model,
            exclude_bool,
            search_depth,
        )

    return gamma_fp, gamma_fpd, gamma_fpdg, age_fpd


# create beta
def creat_variables_beta(families, alpha, gamma_fp, model):
    beta = {}
    for f in families:
        for p in range(len(f.pref)):
            beta[f.id, p] = model.NewBoolVar(f"beta_[{f.id}, {p}]")
            model.Add((beta[f.id, p] == 0)).OnlyEnforceIf(alpha[f.id, p])
            model.Add((beta[f.id, p] == gamma_fp[f.id, p])).OnlyEnforceIf(alpha[f.id, p].Not())
    return beta


# create all variables
def create_variables(children, daycares, families, share_bool, model, exclude_bool, search_depth):
    xfp = creat_variables_xfp(families, model)
    xcd = creat_variables_xcd(children, daycares, families, xfp, model)
    alpha = creat_variables_alpha(families, xfp, model)
    gamma_fp, gamma_fpd, gamma_fpdg, age_fpd = creat_variables_gamma(
        children, daycares, families, share_bool, xcd, alpha, model, exclude_bool, search_depth
    )
    beta = creat_variables_beta(families, alpha, gamma_fp, model)
    return xfp, xcd, alpha, gamma_fp, gamma_fpd, gamma_fpdg, age_fpd, beta


# feasibility constraints for families and daycares
# update Apr 26, 2024
def feasibility_constraints(children, daycares, families, share_bool, xfp, xcd, model):
    # find a set of families with children who prefer to transfer
    f_transfer = []
    for c in children:
        if c.initial_daycare != UNMATCHED_DAYCARE_ID and c.family not in f_transfer:
            f_transfer.append(c.family)

    #  feasibility constraints for families
    for f in families:
        if f.id in f_transfer:
            model.Add(sum(xfp[f.id, p] for p in range(len(f.pref))) == 1)
        else:
            model.Add(sum(xfp[f.id, p] for p in range(len(f.pref))) <= 1)

    #  feasibility constraints for daycares
    for d in daycares:
        rank_dic = d.priority_age_share_dic if share_bool is True else d.priority_age_dic
        for g in range(6):
            if len(rank_dic[g]) != 0:
                if share_bool is False:
                    model.Add(sum(xcd[c_id, d.id] for c_id in rank_dic[g]) <= d.total_numbers[g])
                else:
                    model.Add(sum(xcd[c_id, d.id] for c_id in rank_dic[g]) <= d.total_numbers_share[g])
