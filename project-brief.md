This is a portfolio project to demonstrate deep understanding of kubernetes (k8s) and CI/CD pipelines using the azure
cloud computing platform. It is made as part of a job interview process for RaboBank, a large bank in the Netherlands.

The job is for a Data Engineer building pipelines to serve AI applications and enable agentic tools.

It needs to demonstrate how k8s works, and how CI/CD pipelines should be setup. It is a toy project, demonstrating
scaling, error handling, failover, resilience, load splitting, etc.

The basic idea is to serve an application with 3 parts - a front end, a backend and a database.

I want your advice about what kind of application it could be - it should deal with unstructured data ideally. Perhaps
some text and images inside pdf files, that needs to be extracted, cleaned and validated.

In order to demonstrate the strengths of k8s, we will need to simulate varying amounts of traffic, and simulate memory
leaks, bed deployements, introducing bugs accidentally on purpose. We can have a bit of fun.

We need to plan.

The tool will make use of azure services where necessary as I believe this is what RaboBank does in real life.

I want a dashboard to show what K8s is doing, and metrics about the live system. I want a web ui to be able to control
traffic and what kind of unstructured data is being generated. The whole thing needs to be able to be spun up for
demonstrations and spun down when not in use. the cost per hour should be minimized where possible, to less than 10 euro
per hour, if thats possible.

Lets do some planning and brainstorming.

For the unstructured data, im wondering if we can do some sort of classification of combinations of images, and try to
identify if text is public, confidential, secret, or top secret. Maybe we could create some sort of fun scenario that
would make a team working in a bank smile. Because we need to generate a lot of unstructured data in order to stress test
the system, generation should be fast and cheap - maybe using templates or combining existing elements, rather than
generating everything from scratch.

This is a demo for an interview.
