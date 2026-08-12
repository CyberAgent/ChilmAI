from chilmai.constants import UNMATCHED_DAYCARE_ID


class CP_Child:
    """児童エージェント。

    Attributes:
        id (int): 児童ID。
        age (int): 年齢（0-5）。
        family (int): Family.id。
        initial_daycare (int): 初期割当保育所の Daycare.id。
        pref (list[int]): 希望保育所 ID リスト。
        projected_pref (list[int]): 後で family.pref から作られる投影済み希望リスト。
        all_daycare_ids (list[int]): projected_pref から導出される全保育所 ID。
        assigned_daycare (int | None): CP アルゴリズムによる割当先の Daycare.id。
    """

    def __init__(
        self, c_id: int, age: int, family_id: int, initial_daycare_id: int, preference_list: list[int]
    ):
        # attributes from dictionary
        self.id = c_id
        self.age = age
        self.family = family_id
        self.initial_daycare = initial_daycare_id
        self.pref = [
            d_id if d_id is not None else UNMATCHED_DAYCARE_ID for d_id in preference_list
        ]  # replace None with UNMATCHED_DAYCARE_ID
        # additional attributes
        self.projected_pref = []
        self.all_daycare_ids = []  # notation D(\succ_c)
        self.assigned_daycare = None

    def __str__(self):
        return f"child {self.id}"

    def __repr__(self):
        return f"child {self.id}"

    # notation P(c, d)
    def return_all_positions_of_certain_dacyare_in_projected_pref(self, daycare_id):
        """
        self.projected_pref 内で daycare_id に対応する位置のリストを返す。
        """
        positions = []
        for index, d_id in enumerate(self.projected_pref):
            if d_id == daycare_id and index not in positions:
                positions.append(index)
        return positions


class CP_Daycare:
    """保育所エージェント。

    Attributes:
        id (int): 保育所ID。id=UNMATCHED_DAYCARE_ID のダミー保育所は、児童が未割当になる選択肢を表す。
        recruiting_numbers (list[int]): 年齢ごとの募集人数。各位置が1つの年齢に対応する。
        share_ages_list (list[list[int]]): recruiting_numbers を共有できる年齢グループのリスト。
            例: [[0,1],[4,5]] は0歳と1歳、4歳と5歳が枠を共有できることを表す。
        priority (list[int]): 各保育所の優先順位リスト（child.id のリスト）。
        score_list (list[int]): priority に対応する優先スコアリスト。
        use_transfer (list[bool]): 年齢ごとの転園枠再配分フラグ。
        all_shared_ages (list[int]): share_ages_list を平坦化した年齢リスト。
        total_numbers (list[int]): 年齢ごとに転園希望児童数を追加で含めた数。在園枠の再利用可否に依存する。
        total_numbers_share (list[int]): 年齢枠共有を考慮した total_numbers。
        priority_age_dic (dict): 年齢ごとの優先順位辞書。
        priority_age_share_dic (dict): 年齢枠共有を考慮した年齢ごとの優先順位辞書。
    """

    def __init__(
        self,
        d_id: int,
        recruiting_numbers_list: list[int],
        share_ages_list: list[list[int]],
        priority_child_id_list: list[int],
        priority_score_list: list[int],
        is_use_transfer: list[bool],
    ):
        # attributes from dictionary
        self.id = d_id
        self.recruiting_numbers = recruiting_numbers_list
        self.share_ages_list = share_ages_list
        self.priority = priority_child_id_list
        self.score_list = priority_score_list
        # use_transfer は is True / is False で判定するため、1 や numpy.bool_ が
        # 渡ってもどちらかの分岐が必ず成立するよう bool へ正規化する。
        self.use_transfer = [bool(x) for x in is_use_transfer]

        # additional attributes
        self.all_shared_ages = [age for ages in self.share_ages_list for age in ages]
        self.total_numbers = [x for x in self.recruiting_numbers]
        self.total_numbers_share = [x for x in self.recruiting_numbers]
        self.priority_age_dic = {}
        self.priority_age_share_dic = {}

    def __str__(self):
        return f"daycare {self.id}"

    def __repr__(self):
        return f"daycare {self.id}"

    def update_priority_age_dic(self, children):
        """
        self.priority_list から年齢別の優先順位辞書を作る。

        2024.04.26 の重要な変更:
        c が d に在園しており、かつ c の在園枠を再配分できない場合
        （d.use_transfer[c.age] == False）、c は priority_age_dic に追加しない。
        """

        self.priority_age_dic = {}
        for age in range(6):
            self.priority_age_dic[age] = []

        for c_id in self.priority:
            child = next((c for c in children if c.id == c_id), None)

            ################################################################################
            # exclude the case if child is initially enrolled and occupied seats correspond to his age cannot be reused
            if child.initial_daycare == self.id and self.use_transfer[child.age] is False:
                continue
            ################################################################################

            if c_id not in self.priority_age_dic[child.age]:
                self.priority_age_dic[child.age].append(c_id)

    def update_priority_age_share_dic(self, children):
        """
        self.priority_list から、柔軟な年齢枠共有を考慮した年齢別優先順位辞書を作る。
        """
        if self.share_ages_list is None:
            self.priority_age_share_dic = self.priority_age_dic
        else:
            self.priority_age_share_dic = {}
            for age in range(6):
                self.priority_age_share_dic[age] = []
            # traversing the children in self.priority_child_id_list once
            for c_id in self.priority:
                c = next((c for c in children if c.id == c_id), None)

                ################################################################################
                # exclude the case if child is initially enrolled and occupied seats correspond to his age cannot be reused
                if c.initial_daycare == self.id and self.use_transfer[c.age] is False:
                    continue
                ################################################################################

                if c.age in self.all_shared_ages:
                    for ages in self.share_ages_list:
                        if c.age in ages:  # if c belongs to some group`ages` in self.share_ages_list
                            for age in (
                                ages
                            ):  # add child to each priority_age_share_dic[age] with age in group`ages`
                                if (
                                    c.id not in self.priority_age_share_dic[age]
                                ):  # caution : use `age` instead of `c.age`
                                    self.priority_age_share_dic[age].append(c.id)
                else:
                    if c.id not in self.priority_age_share_dic[c.age]:
                        self.priority_age_share_dic[c.age].append(c.id)

    # notation \hat{G}(d, g)
    def return_related_ages(self, age):
        """
        指定された年齢と同じグループに属する年齢のリストを返す。
        """
        if age in self.all_shared_ages:
            for ages in self.share_ages_list:
                if age in ages:
                    return ages
        else:
            ralted_ages = []
            ralted_ages.append(age)
            return ralted_ages

    # notation C_{better}(d, c, bool)
    def return_better_children_than_child_excluding_siblings(
        self,
        child_id: int,
        children: list[CP_Child],
        allow_share_bool: bool = True,
        exclude_bool: bool = True,
    ) -> list[int]:
        """指定した child_id より優先順位が高い児童の一覧を返す。

        Args:
            child_id: 基準とする child_id。
            children: 全児童リスト。
            allow_share_bool: True の場合、年齢枠共有を考慮した優先順位辞書を使う。
            exclude_bool: True の場合、指定された児童と同じファミリーのきょうだいを除外する。
                定員チェックでのきょうだいの二重カウントを防ぐために True を使う。

        Returns:
            以下を満たす child_id のリスト:
                i) 指定された child_id より優先順位が高い
                ii) allow_share_bool=False の場合は指定された児童と同じ年齢、
                   allow_share_bool=True の場合は定員枠を共有する年齢グループ内
                iii) exclude_bool=True の場合、指定された児童のきょうだいではない
        """
        better_children_id = []
        rank_dic = self.priority_age_share_dic if allow_share_bool is True else self.priority_age_dic
        child = next((c for c in children if c.id == child_id), None)
        pos = rank_dic[child.age].index(child_id)  # find the position of child_id in rank_dic
        for index in range(pos):  # update better_children_id
            c = next((c for c in children if c.id == rank_dic[child.age][index]), None)
            if exclude_bool is True:
                if c.family != child.family and c.id not in better_children_id:  # exclude child's siblings
                    better_children_id.append(c.id)
            else:
                if c.id not in better_children_id:  # include child's siblings
                    better_children_id.append(c.id)
        return better_children_id

    # notation C^{weak}_{better}(d, c, bool)
    def return_weak_better_children_than_child_excluding_siblings(
        self,
        child_id: int,
        children: list[CP_Child],
        allow_share_bool: bool = True,
        exclude_bool: bool = True,
        search_depth: int = 5,
    ) -> list[int]:
        """指定した child_id 以上の優先スコアを持つ児童の一覧を返す（ほぼ同点を含む）。

        Args:
            child_id: 基準とする child_id。
            children: 全児童リスト。
            allow_share_bool: True の場合、年齢枠共有を考慮した優先順位辞書を使う。
            exclude_bool: True の場合、指定された児童と同じファミリーのきょうだいを除外する。
                定員チェックでのきょうだいの二重カウントを防ぐために True を使う。
            search_depth: 同スコアの児童を同順位グループとして探索する追加人数。
                0 のとき同スコアの児童はリスト上の並び順で優先される（位置がタイブレーカーになる）。
                基本は0でよい。
                0 より大きくすると同スコアの児童を同順位グループとして扱い、
                最適化ソルバーがグループ内の入所人数を最大化できるようになるが、
                値が大きいほど計算時間が増加する。

        Returns:
            以下を満たす child_id のリスト:
                i) 指定された child_id より優先順位が高い、
                   またはランクリスト上で search_depth 以内の位置にあり完全に同じスコアを持つ
                ii) allow_share_bool=False の場合は指定された児童と同じ年齢、
                   allow_share_bool=True の場合は定員枠を共有する年齢グループ内
                iii) exclude_bool=True の場合、指定された児童のきょうだいではない
        """
        better_children_id = []
        rank_dic = self.priority_age_share_dic if allow_share_bool is True else self.priority_age_dic
        child = next((c for c in children if c.id == child_id), None)
        pos = rank_dic[child.age].index(child_id)  # find the position of child_id in rank_dic
        # determine how many children with the same priority score but lower priority need to be searched
        end = min(pos + search_depth, len(rank_dic[child.age]))
        for index in range(end):
            c = next((c for c in children if c.id == rank_dic[child.age][index]), None)
            if index < pos:
                if exclude_bool is True:
                    if (
                        c.family != child.family and c.id not in better_children_id
                    ):  # exclude child's siblings
                        better_children_id.append(c.id)
                else:
                    if c.id not in better_children_id:  # include child's siblings
                        better_children_id.append(c.id)
            else:
                child_score = self.score_list[self.priority.index(child.id)]
                c_score = self.score_list[self.priority.index(c.id)]
                if exclude_bool is True:
                    if (
                        c_score == child_score
                        and c.id != child.id
                        and c.family != child.family
                        and c.id not in better_children_id
                    ):
                        better_children_id.append(c.id)
                else:
                    if c_score == child_score and c.id != child.id and c.id not in better_children_id:
                        better_children_id.append(c.id)

        return better_children_id


class CP_Family:
    """家族エージェント。

    Attributes:
        id (int): 家族ID。
        children (list[int]): Child.id のリスト。
        pref (list[list[int]]): 希望順位ごとの Daycare.id リスト（きょうだい人数分の要素を持つ）。
        assignment (list[int] | None): 割当結果の Daycare.id リスト。未割当の場合は None。
        has_siblings (bool): きょうだいがいるかどうか。
    """

    def __init__(
        self,
        f_id: int,
        children_id_list: list = [int],
        pref_list: list = [int],
        assignment_daycare_id_list=None,
    ):
        self.id = f_id
        self.children = children_id_list
        self.pref = pref_list
        self.assignment = assignment_daycare_id_list
        self.has_siblings = len(self.children) > 1

    def __str__(self):
        return f"family {self.id}"

    def __repr__(self):
        return f"family {self.id}"

    # notation D(f, p)
    def return_daycare_id_for_certain_position(self, position):
        """
        family.pref の指定位置にある重複なしの daycare_id 集合を返す。
        """
        disjoint_d_ids = []
        for d_id in self.pref[position]:
            if d_id not in disjoint_d_ids:
                disjoint_d_ids.append(d_id)
        return disjoint_d_ids

    # notation C(f, p, d)
    def return_children_for_certain_position_and_daycare(self, position, daycare_id):
        """
        指定位置で daycare_id に申し込むきょうだい集合を返す。
        """
        children_index = []
        for index, d_id in enumerate(self.pref[position]):
            if d_id == daycare_id and index not in children_index:
                children_index.append(index)
        # convert children_index into children_id
        children_id = []
        for index in children_index:
            children_id.append(self.children[index])
        return children_id

    # notation C(f,p,d,g,bool)
    def return_siblings_for_certain_position_daycare_age(
        self, position, daycare_id, age, share_bool, children, daycares
    ):
        """
        以下を満たすきょうだい集合を返す。
        i) 指定位置で daycare_id に申し込む
        ii) 同じ年齢、または同じ年齢グループに属する
        iii) 在園中だが在園枠を他児童へ再配分できない児童は除外する
        """
        children_id_age = []
        children_id = self.return_children_for_certain_position_and_daycare(position, daycare_id)
        used_ages = []
        daycare = next((d for d in daycares if d.id == daycare_id), None)
        if share_bool is True:
            used_ages = daycare.return_related_ages(age)
        else:
            used_ages = [age]

        # update children_id_age
        if len(children_id) != 0:
            for c_id in children_id:
                child = next((c for c in children if c.id == c_id), None)

                ################################################################################
                # exclude the case if child is initially enrolled and occupied seats correspond to his age cannot be reused
                if child.initial_daycare == daycare_id and daycare.use_transfer[child.age] is False:
                    continue
                ################################################################################

                if child.age in used_ages and child.id not in children_id_age:
                    children_id_age.append(child.id)
        return children_id_age

    # function C_{worst}(f, p, d, g, bool)
    def return_lowest_sibling_for_certain_position_daycare_age(
        self, position, daycare_id, age, share_bool, children_list, daycare_list
    ):
        """
        指定位置で daycare_id に申し込み、同じ年齢または同じ年齢グループに属する
        きょうだいのうち、最も優先順位が低い児童を返す。
        """
        children_id_age = self.return_siblings_for_certain_position_daycare_age(
            position, daycare_id, age, share_bool, children_list, daycare_list
        )
        daycare = next((d for d in daycare_list if d.id == daycare_id), None)
        # determine which priority_dic will be used controlled by share_bool
        rank_dic = daycare.priority_age_share_dic if share_bool is True else daycare.priority_age_dic
        # find the worst child_id
        worst_index = -1
        worst_child_id = -1
        for c_id in children_id_age:
            if rank_dic[age].index(c_id) > worst_index:
                worst_index = rank_dic[age].index(c_id)
                worst_child_id = c_id
        return worst_child_id
