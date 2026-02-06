import os
import sys
import pandas as pd
import numpy as np
import matplotlib as plt
import networkx as nx
import mip


if len(sys.argv) > 1:
    # Prende il percorso del file passato come argomento (es: "Cartella/Edificio1.csv")
    BUILDING_NAME = sys.argv[1] 




ASCENDING_SPEED = 1.0
DESCENDING_SPEED = 2.0
HORIZONTAL_SPEED = 1.5

ASCENDING_ENERGY = 50
DESCENDING_ENERGY = 5
HORIZONTAL_ENERGY = 10

X_BASE_RANGE = range(-8, 6) if "Edificio1.csv" == BUILDING_NAME else range(-10, 11)
Y_BASE_RANGE = range(-17, -14) if "Edificio1.csv" == BUILDING_NAME else range(-31, -29)
Z_BASE = 0

MAX_SECONDS = 7200 if "Edificio1.csv"==BUILDING_NAME else 1500

BATTERY_CAPACITY = 3600 if "Edificio1.csv" == BUILDING_NAME else 21600  # 1 Wh is 3600 J

Y_ENTRY_POINT = -12.5 if "Edificio1.csv" == BUILDING_NAME else -20.0



#reading CSV 
nodes = pd.read_csv(BUILDING_NAME)

#creating bases and entry points
nodes["is_base"] = False
nodes["is_entry_point"] = nodes["y"] <= Y_ENTRY_POINT

# Genero tutte le basi candidate come prima
bases = []
for x in X_BASE_RANGE:
    for y in Y_BASE_RANGE:
        bases.append(
            {"x": x, "y": y, "z": Z_BASE, "is_base": True, "is_entry_point": False}
        )

bases_df = pd.DataFrame(bases)

# Calcolo del centroide sui nodi di servizio
centroid_x = nodes["x"].mean()
centroid_y = nodes["y"].mean()

# Seleziono la base candidata più vicina al centroide (distanza euclidea su x,y)
bases_df["dist_centroid"] = np.hypot(
    bases_df["x"] - centroid_x, bases_df["y"] - centroid_y
)
nearest_idx = bases_df["dist_centroid"].idxmin()
selected_base = bases_df.loc[[nearest_idx]].drop(columns=["dist_centroid"])

# Mantengo solo i nodi di servizio + la base più vicina al centroide
building = pd.concat([nodes, selected_base], ignore_index=True)
active_base = building.index[-1]  # Definisco l'indice della base selezionata

building.to_csv("building.csv", index=False)


#merging nodes to create pairs

building.index += 1
active_base = building.index[
    building["is_base"]
].item()  # Aggiorno active_base dopo lo shift
# Adding is_base and is_entry_point columns

# generating all possible pairs of points (edges)
nodes_pairs = (
    building.rename_axis("source_node")
    .reset_index()
    .merge(building.rename_axis("target_node").reset_index(), how="cross")
)

# removing self-self pairs
nodes_pairs = nodes_pairs[
    nodes_pairs["source_node"] != nodes_pairs["target_node"]
]  # keeping only pairs with different points

first_point_cols = ["x_x", "y_x", "z_x"]
second_point_cols = ["x_y", "y_y", "z_y"]
diff_cols = ["dx", "dy", "dz"]

#computing distances

# function to determine if two points are connected based on distance and coordinate deltas


def process_connections(dataframe):
    # distances and deltas on coordinates
    dataframe[diff_cols] = (
        dataframe[second_point_cols].values - dataframe[first_point_cols].values
    )
    dataframe["euclidean_distance"] = np.sqrt(
        (dataframe[diff_cols] ** 2).sum(axis=1)
    )  # axis=1 sum on columns

    # conditions near and tunnel
    condition_near = dataframe["euclidean_distance"] <= 4.0

    condition_tunnel = (
        ((dataframe["dx"].abs() <= 0.5) & (dataframe["dy"].abs() <= 0.5))
        | ((dataframe["dy"].abs() <= 0.5) & (dataframe["dz"].abs() <= 0.5))
        | ((dataframe["dx"].abs() <= 0.5) & (dataframe["dz"].abs() <= 0.5))
    )

    condition_tunnel_and_not_far = (
        dataframe["euclidean_distance"] <= 11.0
    ) & condition_tunnel

    # if the arc is from base to entry point or viceversa
    condition_base_to_entry_point = (
        (dataframe["is_base_x"]) & (dataframe["is_entry_point_y"])
    ) | ((dataframe["is_base_y"]) & (dataframe["is_entry_point_x"]))

    # l'unica connessione ammessa è base <-> entry point
    condition_involves_base = dataframe["is_base_x"] | dataframe["is_base_y"]

    # Gli archi tra nodi griglia usano le regole di distanza (near/tunnel)
    # Gli archi con basi usano SOLO la regola base <-> entry point
    dataframe["are_connected"] = (
        (condition_near & ~condition_involves_base)
        | (condition_tunnel_and_not_far & ~condition_involves_base)
        | condition_base_to_entry_point
    )
    return dataframe



nodes_pairs = process_connections(nodes_pairs)

nodes_pairs.to_csv("pairs.csv", index=False)



# computing vertical distances on z and distances on horizontal plane x,y
nodes_pairs["d_horizontal"] = np.sqrt(nodes_pairs["dx"] ** 2 + nodes_pairs["dy"] ** 2)
nodes_pairs["d_vertical"] = nodes_pairs["dz"]

# dropping columns that are not useful anymore
nodes_pairs.drop(columns=["dx", "dy", "dz"], inplace=True)
nodes_pairs.drop(columns=["x_x", "y_x", "z_x", "x_y", "y_y", "z_y"], inplace=True)

# keeping only connected pairs
nodes_pairs = nodes_pairs[nodes_pairs["are_connected"] == True]
nodes_pairs.drop(columns=["are_connected"], inplace=True)


#function for time travel

# finding rows corresponding to different movement types

d_horizontal = nodes_pairs["d_horizontal"]
d_vertical = nodes_pairs["d_vertical"]
rows_horizontal = d_vertical == 0
rows_ascending = (d_horizontal == 0) & (d_vertical > 0)
rows_descending = (d_horizontal == 0) & (d_vertical < 0)
rows_oblique_ascending = (d_horizontal != 0) & (d_vertical > 0)
rows_oblique_descending = (d_horizontal != 0) & (d_vertical < 0)


# function for time travel based on movement types and speeds


def compute_time_travel(dataframe):
    dataframe.loc[rows_horizontal, "time_travel"] = (
        dataframe.loc[rows_horizontal, "d_horizontal"] / HORIZONTAL_SPEED
    )

    dataframe.loc[rows_ascending, "time_travel"] = (
        dataframe.loc[rows_ascending, "d_vertical"] / ASCENDING_SPEED
    )
    dataframe.loc[rows_descending, "time_travel"] = (
        -dataframe.loc[rows_descending, "d_vertical"] / DESCENDING_SPEED
    )

    dataframe.loc[rows_oblique_ascending, "time_travel"] = np.maximum(
        dataframe.loc[rows_oblique_ascending, "d_horizontal"] / HORIZONTAL_SPEED,
        dataframe.loc[rows_oblique_ascending, "d_vertical"] / ASCENDING_SPEED,
    )

    dataframe.loc[rows_oblique_descending, "time_travel"] = np.maximum(
        dataframe.loc[rows_oblique_descending, "d_horizontal"] / HORIZONTAL_SPEED,
        -dataframe.loc[rows_oblique_descending, "d_vertical"] / DESCENDING_SPEED,
    )
    return dataframe


# function for energy cost based on movement types and energy consumption rates


def compute_energy_cost(dataframe):
    dataframe.loc[rows_horizontal, "energy_consumption"] = (
        dataframe.loc[rows_horizontal, "d_horizontal"] * HORIZONTAL_ENERGY
    )

    dataframe.loc[rows_ascending, "energy_consumption"] = (
        dataframe.loc[rows_ascending, "d_vertical"] * ASCENDING_ENERGY
    )
    dataframe.loc[rows_descending, "energy_consumption"] = (
        -dataframe.loc[rows_descending, "d_vertical"] * DESCENDING_ENERGY
    )

    dataframe.loc[rows_oblique_ascending, "energy_consumption"] = (
        dataframe.loc[rows_oblique_ascending, "d_horizontal"] * HORIZONTAL_ENERGY
        + dataframe.loc[rows_oblique_ascending, "d_vertical"] * ASCENDING_ENERGY
    )

    dataframe.loc[rows_oblique_descending, "energy_consumption"] = (
        dataframe.loc[rows_oblique_descending, "d_horizontal"] * HORIZONTAL_ENERGY
        + -dataframe.loc[rows_oblique_descending, "d_vertical"] * DESCENDING_ENERGY
    )
    return dataframe


nodes_pairs = compute_time_travel(nodes_pairs)

nodes_pairs = compute_energy_cost(nodes_pairs)

# rounding to 2 decimal places
nodes_pairs["time_travel"] = nodes_pairs["time_travel"].round(2)
nodes_pairs["energy_consumption"] = nodes_pairs["energy_consumption"].round(2)

nodes_pairs.drop(
    columns=["d_horizontal", "d_vertical", "euclidean_distance"], inplace=True
)

# creating directed graph G from the dataframe of edges with costs

G = nx.from_pandas_edgelist(
    nodes_pairs,  # dataframe containing edges
    source="source_node",  # indicating the start of the edge
    target="target_node",  # indicating the end of the edge
    edge_attr=["time_travel", "energy_consumption"],  # edge costs
    create_using=nx.DiGraph(),  # creating an oriented graph
)


from scipy.cluster.vq import kmeans2

if "Edificio1" in BUILDING_NAME:
    K_WANTED=1
else:
    K_WANTED = 4
MAX_CLUSTER_SIZE = 220

service_nodes = building[building["is_base"] == False].index.tolist()
reachable_from_base = nx.single_source_dijkstra_path_length(
    G, active_base, weight="energy_consumption"
)
reachable_to_base = nx.single_source_dijkstra_path_length(
    G.reverse(), active_base, weight="energy_consumption"
)
valid_nodes = [
    n for n in service_nodes if n in reachable_from_base and n in reachable_to_base
]
np.random.seed(90)  # Fissiamo il seed per rendere il clustering deterministico
# 2. K-means Puro: Ogni nodo appartiene a un solo gruppo geografico
coords_array = building.loc[valid_nodes, ["x", "y", "z"]].to_numpy()
centroidi, labels = kmeans2(coords_array, K_WANTED, minit="points", iter=30)

trips = [[] for _ in range(K_WANTED)]
for idx, label in enumerate(labels):
    trips[label].append(valid_nodes[idx])

# 3. Bilanciamento dimensioni (Split dei troppo grandi)
final_trips = []
for t in trips:
    if len(t) > MAX_CLUSTER_SIZE:
        final_trips.append(t[: len(t) // 2])
        final_trips.append(t[len(t) // 2 :])
    elif t:
        final_trips.append(t)

trips = final_trips
TRIPS_READY = True


# LOOP SU TUTTI I CLUSTER
# Per ogni cluster risolviamo un MIP separato
# Usa il modello SCF che funzionava su Edificio1
# Ogni viaggio = 1 sola partenza dalla base → 1 ciclo base→...→base

import math

results = []  # Risultati di ottimizzazione per ogni cluster

for cluster_idx, t_nodes in enumerate(trips, start=1):
   

    # ===============================================================
    # STEP 1: CREIAMO I SET PER QUESTO CLUSTER
    # Aggiungiamo nodi intermedi per garantire connettività base ↔ cluster
    # ===============================================================

    # Filtra: la base NON può essere un nodo di servizio
    # e rimuovi nodi irraggiungibili dalla base (bidirezionalmente)
    S = []
    skipped = []
    for node in t_nodes:
        if node == active_base:
            skipped.append(node)
            continue
        try:
            nx.shortest_path(G, active_base, node, weight="energy_consumption")
            nx.shortest_path(G, node, active_base, weight="energy_consumption")
            S.append(node)
        except nx.NetworkXNoPath:
            skipped.append(node)
    if skipped:
        print(f"  ⚠️ Rimossi {len(skipped)} nodi (base/irraggiungibili): {skipped}")

    # Trova i nodi intermedi necessari per connettere la base ai nodi del cluster
    intermediate_nodes = set()
    for node in S:
        path_to = nx.shortest_path(G, active_base, node, weight="energy_consumption")
        intermediate_nodes.update(path_to)
        path_from = nx.shortest_path(G, node, active_base, weight="energy_consumption")
        intermediate_nodes.update(path_from)

    # N = base + nodi intermedi + nodi di servizio (senza duplicati)
    N_set = set([active_base]) | set(S) | intermediate_nodes
    N = list(N_set)

    # Archi: solo quelli tra nodi del sottografo
    A_set = set()
    for u, v in G.edges:
        if u in N_set and v in N_set:
            A_set.add((u, v))
    A = list(A_set)

    B = [active_base]

    # Nodi di transito: nodi intermedi che NON sono in S e NON sono la base
    transit_nodes = list(N_set - set(S) - set(B))

    # Verifica connettività nel sottografo
    G_sub = nx.DiGraph()
    G_sub.add_edges_from(A)
    unreachable_in_sub = [
        n
        for n in S
        if not nx.has_path(G_sub, active_base, n)
        or not nx.has_path(G_sub, n, active_base)
    ]
    if unreachable_in_sub:
        print(
            f"  ⚠️ {len(unreachable_in_sub)} nodi non raggiungibili nel sottografo, li rimuovo"
        )
        S = [n for n in S if n not in unreachable_in_sub]
        N_set = set([active_base]) | set(S) | intermediate_nodes
        N = list(N_set)
        A_set = set()
        for u, v in G.edges:
            if u in N_set and v in N_set:
                A_set.add((u, v))
        A = list(A_set)
        transit_nodes = list(N_set - set(S) - set(B))

    

    # ===============================================================
    # STEP 2: CREIAMO IL MODELLO MIP PER QUESTO CLUSTER
    # ===============================================================
    m = mip.Model(f"DroneTourPlanning_Cluster_{cluster_idx}", solver_name=mip.CBC)
    m.threads = -1
    m.verbose = 0 # Disattiva il log del solver
    m.max_mip_gap = 100  # Ferma appena trova una soluzione ammissibile

    # Parametri per questo cluster
    t = {
        (u, v): data["time_travel"]
        for u, v, data in G.edges(data=True)
        if (u, v) in A_set
    }
    e = {
        (u, v): data["energy_consumption"]
        for u, v, data in G.edges(data=True)
        if (u, v) in A_set
    }
    C = BATTERY_CAPACITY

    # Calcola H: ogni tour ha 1 sola partenza dalla base, vincolato da batteria.
    # Stima: per ogni nodo calcola il costo A/R minimo dalla base.
    # H = massimo tra ceil(sum_min_energies / C) e ceil(|S| / max_nodi_per_tour)
    min_roundtrip = {}
    for i in S:
        try:
            d_to = nx.shortest_path_length(
                G, active_base, i, weight="energy_consumption"
            )
            d_from = nx.shortest_path_length(
                G, i, active_base, weight="energy_consumption"
            )
            min_roundtrip[i] = d_to + d_from
        except nx.NetworkXNoPath:
            min_roundtrip[i] = C  # worst case

    # Stima: quanti nodi può visitare un singolo tour?
    # Il tour più costoso: nodo più lontano dalla base ha costo A/R = max_roundtrip
    # Nodi rimanenti hanno costo incrementale ≈ min arco in/out
    min_energy_in_out = {}
    for i in S:
        incoming = [e[j, i] for j in N if (j, i) in A_set]
        outgoing = [e[i, j] for j in N if (i, j) in A_set]
        min_energy_in = min(incoming) if incoming else 0
        min_energy_out = min(outgoing) if outgoing else 0
        min_energy_in_out[i] = min_energy_in + min_energy_out

    sum_min_energies = sum(min_energy_in_out.values())
    # Aggiungiamo il costo base A/R medio per ogni tour
    avg_base_roundtrip = (
        sum(min_roundtrip.values()) / len(min_roundtrip) if min_roundtrip else C
    )
    # Ogni tour costa almeno: costo_AR_base + costi_nodi_visitati
    # Approssimazione: H = ceil((sum_energies + H * avg_base_cost) / C)
    # → H = ceil(sum_energies / (C - avg_base_cost))
    effective_capacity = max(C - avg_base_roundtrip, C * 0.3)
    H_length = 1  # Un solo viaggio per cluster
    H = list(range(1, H_length + 1))

    

    # ===============================================================
    # VARIABLES
    # ===============================================================
    x = {
        (i, j, h): m.add_var(var_type=mip.BINARY, name=f"x_{i}_{j}_{h}")
        for i, j in A
        for h in H
    }

    b = {i: m.add_var(var_type=mip.BINARY, name=f"b_{i}") for i in B}

    # SCF (Single Commodity Flow) variables for subtour elimination
    # Upper bound = len(N) perché ogni nodo attraversato (servizio o transito) consuma flusso
    f = {
        (i, j, h): m.add_var(lb=0, ub=len(N), name=f"f_{i}_{j}_{h}")
        for i, j in A
        for h in H
    }

    # ===============================================================
    # OBJECTIVE FUNCTION
    # ===============================================================
    m.objective = mip.minimize(mip.xsum(t[i, j] * x[i, j, h] for i, j in A for h in H))

    # ===============================================================
    # CONSTRAINTS
    # ===============================================================

    # (1) Only one base is selected
    m += mip.xsum(b[i] for i in B) == 1

    # (2) Each service node is visited at least once
    for i in S:
        m += mip.xsum(x[j, i, h] for j in N for h in H if (j, i) in A_set) >= 1

    # (3) Flow conservation for x (arc variables)
    for i in N:
        for h in H:
            m += mip.xsum(x[j, i, h] for j in N if (j, i) in A_set) == mip.xsum(
                x[i, j, h] for j in N if (i, j) in A_set
            )

    # (4) Il tour DEVE partire dalla base (almeno 1 arco uscente)
    # Con SCF + conservazione flusso, il tour è comunque connesso e chiuso.
    # La base può essere attraversata più volte (hub) nel grafo sparso.
    for base in B:
        for h in H:
            m += mip.xsum(x[base, j, h] for j in N if (base, j) in A_set) == b[base]

    # (5) Energy constraint
    for h in H:
        m += mip.xsum(e[i, j] * x[i, j, h] for (i, j) in A) <= C

    # (6) SCF Subtour Elimination

    # (6a) f_ij <= |N| * x_ij (flusso solo su archi attivi)
    for i, j in A:
        for h in H:
            m += f[i, j, h] <= len(N) * x[i, j, h]

    # (6b) SCF flow conservation:
    # - Nodi di SERVIZIO: inflow_f - outflow_f = visits (consumano flusso)
    # - Nodi di TRANSITO: inflow_f - outflow_f = 0 (conservano flusso, no consumo)
    # Questo impedisce sottocircuiti (flusso non può ricaricarsi) ed evita
    # l'infeasibility dell'SCF unificato (che forzava consumo anche ai transiti).
    S_set = set(S)
    for i in S:
        for h in H:
            inflow = mip.xsum(f[j, i, h] for j in N if (j, i) in A_set)
            outflow = mip.xsum(f[i, j, h] for j in N if (i, j) in A_set)
            visits = mip.xsum(x[j, i, h] for j in N if (j, i) in A_set)
            m += inflow - outflow == visits

    for i in transit_nodes:
        for h in H:
            inflow = mip.xsum(f[j, i, h] for j in N if (j, i) in A_set)
            outflow = mip.xsum(f[i, j, h] for j in N if (i, j) in A_set)
            m += inflow - outflow == 0

    # (7) Symmetry Breaking
    for h in range(len(H) - 1):
        m += mip.xsum(x[i, j, H[h]] for (i, j) in A) >= mip.xsum(
            x[i, j, H[h + 1]] for (i, j) in A
        )

  

    status = m.optimize(max_seconds=MAX_SECONDS)

    results.append(
        {
            "cluster": cluster_idx,
            "nodes": S,
            "N": N,
            "A": A,
            "H": H,
            "status": status,
            "objective": m.objective_value,
            "model": m,
            "x_vars": x,
        }
    )


# base unica già determinata
active_base = B[0]
# definisco per salvare i vari percorsi (path1, path2...)
all_paths = []

# Itero sui risultati come se fossero i viaggi H (ogni cluster = un viaggio)
for idx, res in enumerate(results, start=1):
    m_cluster = res["model"]
    
    if m_cluster.num_solutions:
        x_cluster = res["x_vars"]
        H_cluster = res["H"]
        A_cluster = res["A"]
        
        for h in H_cluster:
            # dizionario per salvare il nodo prossimo j dato il nodo i
            next_node = {}
            for i, j in A_cluster:
                if x_cluster[i, j, h].x is not None and x_cluster[i, j, h].x >= 0.99:
                    # se è il primo arco creo una lista
                    if i not in next_node:
                        next_node[i] = []
                    # inserisco il nodo di arrivo j dato il nodo di partenza i
                    # li metto in una lista perché dato un nodo i questo può avere più trasnizione di output
                    next_node[i].append(j)

            # next_node[i] è la lista di tutti i nodi raggiungibili da i

            # lo stack sono i nodi da esplorare, parto dalla base
            stack = [active_base]
            path = []

            # finche c'è qualcosa nello stack vado avanti
            while stack:
                v = stack[-1]  # prendo ultimo elemento
                if v in next_node and next_node[v]:  # se v ha ancora archi non usati

                    u = next_node[
                        v
                    ].pop()  # prendo un nodo target (un arco) e lo rimuovo dalla lista
                    stack.append(u)  # metto la destinazione nello stack
                else:
                    # se non ha archi uscenti li ho già esplorati e la inserisco nello stack
                    path.append(stack.pop())

            # il percorso è al contrario
            path = path[::-1]

            path_str = ["0"]  # base
            for node in path[1:]:
                if node == active_base:
                    path_str.append("-0")
                else:
                    path_str.append("-" + str(node))

            print(f"Viaggio {idx}: {''.join(path_str)}")
            all_paths.append(path)
    


import matplotlib.pyplot as plt
import matplotlib.lines as mlines  # Import necessario per le custom legend

# creo una lista delle basi da rimuovere

remove_bases = [b for b in B if b != active_base]
# print(basi_da_rimuovere)

# creo il grafo senza le basi
G_sub = G.copy()
G_sub.remove_nodes_from(remove_bases)

plt.figure(figsize=(18, 14))

# k controlla la distanza tra i nodi
pos = nx.spring_layout(G_sub, k=2.5, iterations=100, seed=42)


node_colors = ["red" if n == active_base else "skyblue" for n in G_sub.nodes()]

# 0 se è la base altrimenti i valore del nodo
labels = {n: (0 if n == active_base else n) for n in G_sub.nodes()}

# Estrai gli archi dai path
path_edges = [[] for _ in all_paths]  # lista di archi per ogni path



# Usa tab20 se ci sono pochi percorsi, altrimenti usa hsv per averne di più
if len(all_paths) <= 20:
    cmap = plt.colormaps['tab20']
    colors_path = [cmap(i/20) for i in range(len(all_paths))]
else:
    cmap = plt.colormaps['hsv']
    colors_path = [cmap(i/len(all_paths)) for i in range(len(all_paths))]

for idx, path in enumerate(all_paths):

    # all_paths contiene già liste di interi
    # creo coppie di archi
    for i in range(len(path) - 1):
        path_edges[idx].append((path[i], path[i + 1]))

# disegno i nodi
nx.draw_networkx_nodes(G_sub, pos, node_size=400, node_color=node_colors)
nx.draw_networkx_labels(G_sub, pos,labels=labels, font_size=10, font_weight="bold")

# Crea una lista per gli handle della legenda
legend_handles = []

# archi dei path
for idx, edges in enumerate(path_edges):
    if not edges: continue # Salta path vuoti
    
    # Aggiungi handle manuale per la legenda
    line = mlines.Line2D([], [], color=colors_path[idx], linewidth=2.5, label=f"Viaggio {idx+1}")
    legend_handles.append(line)
    
    nx.draw_networkx_edges(
        G_sub,
        pos,
        edgelist=edges,
        edge_color=[colors_path[idx]],
        arrows=True,
        arrowsize=20,
        width=2.5,
        # label=f"Viaggio {idx+1}", # Non necessario se usiamo handles custom
    )

plt.title(f"Grafo con base {active_base} - Viaggi colorati", fontsize=16)
# Passa esplicitamente gli handle alla legenda
plt.legend(handles=legend_handles, fontsize=12, loc='best', title="Percorsi")
plt.tight_layout()
# plt.show() # Disabilitato per evitare errore FigureCanvasAgg
# output_img = f"solution_{os.path.basename(BUILDING_NAME).replace('.csv', '')}.png"
# plt.savefig(output_img)
# print(f"Grafico salvato in: {output_img}")
plt.show()

