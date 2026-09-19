# PhotoPiler spec for Claude Code

Our goal is to write a web app in Python that we can then host somewhere
that people elsewhere can access it on the open internet. This is purely for demonstration purposes so the hosting doesn't need to scale.

The app will take a collection of photos and render an image of those
photos in a haphazard pile with various rotations, to look like they are
partially sitting on top of one another, something like
@doc/example_photo_pile.png. The positions and rotations should be chosen
at random. It is okay if parts of some photos are cropped off the edge
of the target photo. We'll do some math to not put photos closer to the
edge of the target image than a quarter of their width, or something like
that.

The inputs will be standard digital images in common formats such as
JPG and PNG. There should also be a demo mode in which the user can load
the images in the @demo_inputs directory instead of their own.

The size of the target image should be the sum of the areas of the input
images, multiplied by some fraction. Initially that fraction can be
hardcoded as a variable in the code; later we will give the user control
over it.

The user should be able to choose whether each image should be rendered:
- With Polaroid-style borders (white border, thicker at the bottom)
- With instamatic-style borders (single-thickness white border)
- With no borders
- Or with the border chosen at random for each photo

The user should also be able to choose whether each image should be
rendered in color or in monochrome, or with color vs. monochrome
chosen at random for each photo.

We will also optionally apply image processing to make the photos look
older. This involves reducing saturation and adding noise. A web search
will find ways to do this in common Python image processing libraries
or I can help.

The user should also be able to choose how much of thise image processing
we apply: none, light, medium, heavy, or randomly chosen for each photo.

It is important to sequence this project so that we have a usable MVP as
quickly as possible, and then to add on features from there. Specifically
I would like to sequence the project like this:
1. The basic web app that takes the images from @demo_inputs and renders
a basic "photo pile" image with random rotations and positions, but no
image processing or borders.
2. Add borders, and then user control of them.
3. Add color vs. monochrome, and then user control of it.
4. Add the image processing to make the photos look old, and then user
control of it.
5. Add user control over the multiplier that determines the size of the
target image.
6. Add the ability for the user to upload their own photos instead of
using the demo inputs.
