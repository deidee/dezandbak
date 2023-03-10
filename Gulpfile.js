'use strict';

const gulp = require('gulp');
let less = require('gulp-less');
const sass = require('gulp-sass')(require('sass'));

gulp.task('less', function () {
    return gulp.src('./less/**/*.less')
        .pipe(less())
        .pipe(gulp.dest('./css'));
});

gulp.task('sass', function () {
    return gulp.src(['./**/*.scss', '!node_modules/**/*'])
        .pipe(sass({includePaths: ['node_modules'], outputStyle: 'expanded'}))
        .pipe(gulp.dest('./'));
});

gulp.task('sass:watch', function() {
    gulp.watch('./**/*.scss', gulp.series('sass'));
});
