/*
 * Sample source documents for the Video Nuggets demo.
 *
 * These are ORIGINAL, generic explainers written for this prototype. They are
 * deliberately not copied from any book or site. They describe widely-known,
 * vendor-neutral infrastructure concepts so the pipeline has realistic,
 * heading-structured input to chew on. The Nutanix Bible is referenced in the
 * README only as a public example of the kind of doc this tool is built for.
 */
window.VN_SAMPLES = [
  {
    id: "hci-basics",
    label: "What is Hyperconverged Infrastructure?",
    minutes: "~3 min nugget",
    text: `What is Hyperconverged Infrastructure?

Traditional data centers keep three things in separate boxes: servers that do the thinking, storage arrays that hold the data, and a network that wires them together. Each box is bought, managed, and scaled on its own. That separation made sense decades ago, but it creates silos, slow procurement, and a lot of specialist hand-offs.

Hyperconverged infrastructure, or HCI, collapses compute and storage into a single type of building block called a node. You start with a few nodes, and when you need more capacity you simply add another node. The software stitches all of the nodes together into one pool.

The Building Block: Nodes and Clusters

A node is just an industry-standard server with CPUs, memory, and local drives. On its own a node is not very interesting. The magic happens when you group several nodes into a cluster.

A cluster behaves like one large, reliable computer even though it is made of many independent machines. If one node fails, the others keep serving the workloads that were running on it. Capacity, performance, and resilience all grow as you add nodes, which is why people call this a scale-out model.

The Distributed Storage Layer

In HCI, there is no central storage array. Instead, every node contributes its local drives to a shared, distributed storage pool that spans the whole cluster. A software layer running on each node turns that pile of local disks into one virtual storage system that every virtual machine can use.

To keep data safe, the system writes more than one copy of each piece of data and spreads those copies across different nodes. If a drive or a whole node dies, another copy is always available, and the cluster quietly rebuilds the missing copy in the background. Users never notice.

Why Teams Choose HCI

The first reason is simplicity. One team can manage compute, storage, and virtualization from a single console instead of juggling three separate systems and three separate vendors.

The second reason is predictable growth. Because you scale by adding identical nodes, capacity planning becomes a straight line rather than a guessing game about giant, expensive arrays.

The third reason is resilience. Redundant copies and self-healing mean the cluster tolerates hardware failure as a normal, expected event rather than a late-night emergency.`,
  },
  {
    id: "virtualization",
    label: "Virtualization & the Hypervisor",
    minutes: "~2 min nugget",
    text: `Virtualization and the Hypervisor

For a long time, every application got its own physical server. Most of those servers sat almost idle, using a small slice of their power while still drawing electricity and taking up space. It was wasteful and slow to change.

Virtualization fixes this by letting one physical machine pretend to be many. A thin layer of software creates virtual machines, each of which believes it has its own dedicated computer.

What the Hypervisor Does

The hypervisor is the software that creates and runs virtual machines. It sits between the physical hardware and the virtual machines, handing out slices of CPU, memory, and storage to each one and keeping them isolated from each other.

Because the hypervisor controls the hardware, it can do clever things: pause a running machine, move it to a different host without downtime, or instantly create a copy. The virtual machines themselves never have to know any of this is happening.

Pooling and Scheduling Resources

When many hosts run a hypervisor and are joined together, their CPUs and memory form one large pool. A scheduler decides which host should run each virtual machine, balancing the load so no single host is overwhelmed while others sit empty.

If a host needs maintenance, its virtual machines simply migrate to other hosts first. If a host fails unexpectedly, the affected machines restart automatically elsewhere. The result is that hardware becomes a flexible, shared resource instead of a fixed assignment.`,
  },
  {
    id: "management-plane",
    label: "The Management Plane",
    minutes: "~2 min nugget",
    text: `The Management Plane

A modern cluster has a lot of moving parts: dozens of nodes, hundreds of virtual machines, storage policies, and networking rules. Without a single place to see and control all of it, operators would drown in dashboards.

The management plane is that single place. It is the control tower that gives operators one view of the entire system and one set of controls to run it.

One Console, Many Jobs

From the management console an operator can create a new virtual machine, check the health of every node, watch performance trends, and set policies that apply across the whole cluster. Tasks that once required logging into many separate tools now happen in one workflow.

Good management planes also explain themselves. Instead of just raising an alarm, they point to the likely cause and suggest the next step, so even a small team can run a large environment confidently.

Automation and APIs

Clicking buttons is fine for one machine, but real operations need repeatable automation. Every action in a good management plane is also available through an API, which is simply a doorway that lets other software make the same requests a human would.

With APIs, teams script the boring, repetitive work: provisioning fleets of machines, applying updates on a schedule, or wiring the cluster into their existing tools. The console is for people; the API is for the scripts and pipelines that do the heavy lifting.`,
  },
];
