import sys

#check dependencies 
required_packages = {
    'pandas': 'pandas',
    'numpy': 'numpy', 
    'matplotlib': 'matplotlib',
    'networkx': 'networkx',
    'mip': 'mip',
    'scipy': 'scipy'
}

missing_packages = []
for package_name, import_name in required_packages.items():
    try:
        __import__(import_name)
    except ImportError:
        missing_packages.append(package_name)

if missing_packages:
    print("=" * 60)
    print("ERROR: Missing Python packages")
    print("\nThe following packages must be installed:")
    for pkg in missing_packages:
        print(f"- {pkg}")
    print("\nTo install them, run:")
    print("\tpip install -r requirements.txt")

    print("\nOr:")
    print(f"\tpip install {' '.join(missing_packages)}")
    print("=" * 60)
    sys.exit(1)

#import libreries
import os
import sys
import pandas as pd
import numpy as np
import networkx as nx
import mip
from scipy.cluster.vq import kmeans2
import math
import matplotlib.pyplot as plt
import matplotlib.lines as mlines 
from mpl_toolkits.mplot3d import Axes3D
import plotly.graph_objects as go

#path to execute the script
script_dir = os.path.dirname(os.path.abspath(__file__))
#print(f"Script directory: {script_dir}")

if len(sys.argv) > 1:
    #takes second argument, the building
    file_path = sys.argv[1]
    BUILDING_NAME = os.path.basename(file_path)

if BUILDING_NAME not in ["building_1.csv", "building_2.csv"]:
    print("Wrong filename, available files: [ building_1.csv | building_2.csv ]")
    sys.exit(1)
else: 
    print(f"Processing {BUILDING_NAME}")

ASCENDING_SPEED = 1.0
DESCENDING_SPEED = 2.0
HORIZONTAL_SPEED = 1.5

ASCENDING_ENERGY = 50
DESCENDING_ENERGY = 5
HORIZONTAL_ENERGY = 10

X_BASE_RANGE = range(-8, 6) if "building_1.csv" == BUILDING_NAME else range(-10, 11)
Y_BASE_RANGE = range(-17, -14) if "building_1.csv" == BUILDING_NAME else range(-31, -29)
Z_BASE = 0

MAX_SECONDS = 6000 if "building_1.csv"==BUILDING_NAME else 1500

BATTERY_CAPACITY = 3600 if "building_1.csv" == BUILDING_NAME else 21600  # 1 Wh is 3600 J

Y_ENTRY_POINT = -12.5 if "building_1.csv" == BUILDING_NAME else -20.0


#print("preprocessing data and building graph...")

#reading CSV 
file_path = os.path.join(script_dir, "../data", BUILDING_NAME)
nodes = pd.read_csv(file_path)

#creating bases and entry points
nodes["is_base"] = False
nodes["is_entry_point"] = nodes["y"] <= Y_ENTRY_POINT

#generate all candidates bases
bases = []
for x in X_BASE_RANGE:
    for y in Y_BASE_RANGE:
        bases.append(
            {"x": x, "y": y, "z": Z_BASE, "is_base": True, "is_entry_point": False}
        )

bases_df = pd.DataFrame(bases)

# calculate the centroids on the service nodes
centroid_x = nodes["x"].mean()
centroid_y = nodes["y"].mean()

# I select the candidate base closest to the centroid, based on Euclidean distance
bases_df["dist_centroid"] = np.hypot(
    bases_df["x"] - centroid_x, bases_df["y"] - centroid_y
)
nearest_idx = bases_df["dist_centroid"].idxmin()
selected_base = bases_df.loc[[nearest_idx]].drop(columns=["dist_centroid"])

#keep only service nodes and the selected base
building = pd.concat([nodes, selected_base], ignore_index=True)
active_base = building.index[-1]  #the index of the selected base

#merging nodes to create pairs

building.index += 1
active_base = building.index[
    building["is_base"]
].item()  


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

    #the only possible connection is base <-> entry points
    condition_involves_base = dataframe["is_base_x"] | dataframe["is_base_y"]

    # edges between grid nodes use distance rules (near/tunnel)
    # edges with bases use only the base rule <-> entry point
    dataframe["are_connected"] = (
        (condition_near & ~condition_involves_base)
        | (condition_tunnel_and_not_far & ~condition_involves_base)
        | condition_base_to_entry_point
    )
    return dataframe

nodes_pairs = process_connections(nodes_pairs)

# computing vertical distances on z and distances on horizontal plane x,y
nodes_pairs["d_horizontal"] = np.sqrt(nodes_pairs["dx"] ** 2 + nodes_pairs["dy"] ** 2)
nodes_pairs["d_vertical"] = nodes_pairs["dz"]

# dropping columns that are not useful anymore
nodes_pairs.drop(columns=["dx", "dy", "dz"], inplace=True)
nodes_pairs.drop(columns=["x_x", "y_x", "z_x", "x_y", "y_y", "z_y"], inplace=True)

# keeping only connected pairs
nodes_pairs = nodes_pairs[nodes_pairs["are_connected"] == True]
nodes_pairs.drop(columns=["are_connected"], inplace=True)


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



if "building_1" in BUILDING_NAME:
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
np.random.seed(90)  #set the seed 
# k-means: each node belongs to a specific cluster 
coords_array = building.loc[valid_nodes, ["x", "y", "z"]].to_numpy()
centroidi, labels = kmeans2(coords_array, K_WANTED, minit="points", iter=30)

trips = [[] for _ in range(K_WANTED)]
for idx, label in enumerate(labels):
    trips[label].append(valid_nodes[idx])

# balancing dimensions
final_trips = []
for t in trips:
    if len(t) > MAX_CLUSTER_SIZE:
        final_trips.append(t[: len(t) // 2])
        final_trips.append(t[len(t) // 2 :])
    elif t:
        final_trips.append(t)

trips = final_trips
TRIPS_READY = True


# loop on all clusters
#for each cluster we solve a seperate MIP (heuristic way)

results = []  #results for each cluster

print("Running MIP optimizer...")

for cluster_idx, t_nodes in enumerate(trips, start=1):

    # base cannot be a service node
    # and remove unreachable nodes from the base 
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
        print(f"  ⚠️ Removed {len(skipped)} nodes (base/unreachable): {skipped}")

    # find the intermediate nodes needed to connect the base to the cluster nodes
    intermediate_nodes = set()
    for node in S:
        path_to = nx.shortest_path(G, active_base, node, weight="energy_consumption")
        intermediate_nodes.update(path_to)
        path_from = nx.shortest_path(G, node, active_base, weight="energy_consumption")
        intermediate_nodes.update(path_from)

    # N = base + intermediate nodes + service nodes (without duplicates)
    N_set = set([active_base]) | set(S) | intermediate_nodes
    N = list(N_set)

    # only edges between thos who belongs to the sub-graph
    A_set = set()
    for u, v in G.edges:
        if u in N_set and v in N_set:
            A_set.add((u, v))
    A = list(A_set)

    B = [active_base]

    #nodes which are not in S and are not the base
    transit_nodes = list(N_set - set(S) - set(B))

    #verify connectivity
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
            f"  {len(unreachable_in_sub)} nodes unreachable in subgraph, removing them"
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

    #create mip for this cluster
    m = mip.Model(f"DroneTourPlanning_Cluster_{cluster_idx}", solver_name=mip.CBC)
    m.threads = 1
    m.verbose = 0
    m.max_mip_gap = 0.3  

    #parameters for this cluster
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
    H_length = 1  #one subtour(travel) for each cluster
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
    # upper bound = len(N) because each node traversed (service or transit) consumes flow
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

    # (4) The tour MUST start from the base (at least 1 outgoing bow)
    # With SCF + flow preservation, the tour is still connected and closed.
    # The base can be traversed multiple times (hubs) in the sparse graph.
    for base in B:
        for h in H:
            m += mip.xsum(x[base, j, h] for j in N if (base, j) in A_set) == b[base]

    # (5) Energy constraint
    for h in H:
        m += mip.xsum(e[i, j] * x[i, j, h] for (i, j) in A) <= C

    # (6) SCF Subtour Elimination

    # (6a) f_ij <= |N| * x_ij 
    for i, j in A:
        for h in H:
            m += f[i, j, h] <= len(N) * x[i, j, h]

    # (6b) SCF flow conservation:
    # - SERVICE nodes: inflow_f - outflow_f = visits (consume flow)
    # - TRANSIT nodes: inflow_f - outflow_f = 0 (preserve flow, no consumption)
    # This prevents subcircuits (flow cannot recharge) and avoids
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

#print("Optimization completed for all clusters. preparing visualization...")

# unique base
active_base = B[0]
# to save all different paths
all_paths = []


for idx, res in enumerate(results, start=1):
    m_cluster = res["model"]
    
    if m_cluster.num_solutions:
        x_cluster = res["x_vars"]
        H_cluster = res["H"]
        A_cluster = res["A"]
        
        for h in H_cluster:
            # dictionary to save the next node j given node i
            next_node = {}
            for i, j in A_cluster:
                if x_cluster[i, j, h].x is not None and x_cluster[i, j, h].x >= 0.99:
                    #if it is the first edge, create a list
                    if i not in next_node:
                        next_node[i] = []
                    #insert the arrival node j given the departure node i
                    # put them in a list because given a node i this can have multiple output transnitions
                    next_node[i].append(j)

            # next_node[i] is the list of all nodes reachable from i

            # node to explore, starting from base
            stack = [active_base]
            path = []

           
            while stack:
                v = stack[-1]  # take last element
                if v in next_node and next_node[v]:  

                    u = next_node[
                        v
                    ].pop()  # 
                    stack.append(u)  # put the destination in the stack
                else:
                    # if it doesn't have outgoing edges it has already explored them and put it on the stack
                    path.append(stack.pop())

            #reverse the path
            path = path[::-1]

            path_str = ["0"]  # base
            for node in path[1:]:
                if node == active_base:
                    path_str.append("-0")
                else:
                    path_str.append("-" + str(node))

            print(f"Trip {idx}: {''.join(path_str)}")
            all_paths.append(path)
    

#list of the bases to remove

remove_bases = [b for b in B if b != active_base]


# setup figure 
fig = plt.figure(figsize=(12, 8))
ax = fig.add_subplot(111, projection='3d')

# creating graph  
G_sub = G.copy()
G_sub.remove_nodes_from(remove_bases)

pos_3d = {node: (building.loc[node, 'x'], building.loc[node, 'y'], building.loc[node, 'z']) 
          for node in G_sub.nodes()}

#colors
if len(all_paths) <= 10:
    cmap = plt.colormaps['tab10']
elif len(all_paths) <= 20:
    cmap = plt.colormaps['tab20']
else:
    cmap = plt.colormaps['hsv']

# seprating base from different nodes
service_nodes = [n for n in G_sub.nodes() if n != active_base]


xs = [pos_3d[n][0] for n in service_nodes]
ys = [pos_3d[n][1] for n in service_nodes]
zs = [pos_3d[n][2] for n in service_nodes]

# base
base_x, base_y, base_z = pos_3d[active_base]

# draw nodes
ax.scatter(xs, ys, zs, c='skyblue', s=20, edgecolors='black',
           alpha=0.8, depthshade=True, label='Service Nodes')
#draw base
ax.scatter(base_x, base_y, base_z, c='magenta', s=180, marker='^',
           edgecolors='black', depthshade=False, label='Base', zorder=5)

# adding labels
for node in G_sub.nodes():
    label = "0" if node == active_base else str(node)
    ax.text(pos_3d[node][0], pos_3d[node][1], pos_3d[node][2], label, size=8, zorder=1)

# draw paths 
for idx, path in enumerate(all_paths):
    if len(path) < 2:
        continue
    
    
    color = cmap(idx / len(all_paths)) if len(all_paths) > 20 else cmap(idx)
    
    #extract coordinates
    p_x = [pos_3d[node][0] for node in path]
    p_y = [pos_3d[node][1] for node in path]
    p_z = [pos_3d[node][2] for node in path]
    
    
    ax.plot(p_x, p_y, p_z, color=color, linewidth=2, label=f'Trip {idx+1}')

# set visualization
ax.set_title("3D Graph")
ax.set_xlabel('X')
ax.set_ylabel('Y')
ax.set_zlabel('Z')

ax.set_box_aspect((max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs))) 
#index to better understand
ax.legend(loc='center left', bbox_to_anchor=(1.07, 0.5), title="Legend")

plt.tight_layout()
save_path = f"docs/{BUILDING_NAME.replace('.csv', '')}_plot.png"
plt.savefig(save_path, bbox_inches='tight', dpi=300)
print(f"Plot saved to {save_path}")
plt.show()

