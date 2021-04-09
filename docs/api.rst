API Reference
=============

.. warning::

    Ideally this should auto-generate API documenation for the whole package.
    However, as currently set up, `import catkit` doesn't import the submodules in
    ``__init__``, so this doesn't work automatically. We will have to change this, or
    else individually import the particular files and objects we want to have API
    documentation generated for. Here's an example of doing that for a few things:

.. automodapi:: catkit

The above does not auto generate anything, though it would be nice if it did.

.. automodapi:: catkit.hardware
.. automodapi:: catkit.interfaces

Nor do those.

.. automodapi:: catkit.interfaces.DeformableMirrorController
.. automodapi:: catkit.interfaces.DeformableMirrorController
.. automodapi:: catkit.hardware.newport.NewportMotorController


Those work, but the output has redundant copies of ABC and other parent classes.
